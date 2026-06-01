const cp = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vscode = require('vscode');

let diagnostics;
let output;
let statusItem;
const validationTimers = new Map();

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection('flowspec');
  output = vscode.window.createOutputChannel('FlowSpec');
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusItem.text = '$(symbol-event) FlowSpec';
  statusItem.tooltip = 'FlowSpec extension is active. Click to preview generated TLA+.';
  statusItem.command = 'flowspec.previewTla';

  context.subscriptions.push(diagnostics, output, statusItem);
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.validateCurrent', () => validateCurrent(context, true)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.compileCurrent', () => compileCurrent(context)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.previewTla', () => previewTla(context)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.showParseTree', () => showParseTree(context)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.runSuite', () => runSuite(context, false)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.runTlcCurrent', () => runTlcCurrent(context)));
  context.subscriptions.push(vscode.commands.registerCommand('flowspec.runTlcSuite', () => runSuite(context, true)));
  context.subscriptions.push(vscode.languages.registerCompletionItemProvider(
    { language: 'flowspec', scheme: 'file' },
    createCompletionProvider(),
    ':',
    ' ',
  ));

  context.subscriptions.push(vscode.workspace.onDidOpenTextDocument((document) => validateDocument(context, document)));
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument((document) => validateDocument(context, document)));
  context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(() => updateStatusItem()));
  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument((event) => {
    if (!configValue('validateOnChange', true)) {
      return;
    }
    scheduleValidation(context, event.document);
  }));

  for (const document of vscode.workspace.textDocuments) {
    validateDocument(context, document);
  }
  updateStatusItem();
}

function deactivate() {}

async function validateCurrent(context, showSuccess) {
  const document = activeFlowSpecDocument();
  if (!document) {
    return;
  }
  await validateDocument(context, document, showSuccess);
}

async function compileCurrent(context) {
  const document = activeFlowSpecDocument();
  if (!document) {
    return;
  }
  try {
    const result = await runParseTool(context, document, []);
    output.clear();
    output.appendLine(result.stdout);
    output.show(true);
  } catch (error) {
    showToolError(error);
  }
}

async function previewTla(context) {
  const document = activeFlowSpecDocument();
  if (!document) {
    return;
  }
  try {
    const result = await runParseTool(context, document, []);
    const preview = await vscode.workspace.openTextDocument({
      content: result.stdout,
      language: 'plaintext',
    });
    await vscode.window.showTextDocument(preview, { preview: true, viewColumn: vscode.ViewColumn.Beside });
  } catch (error) {
    showToolError(error);
  }
}

async function showParseTree(context) {
  const document = activeFlowSpecDocument();
  if (!document) {
    return;
  }
  try {
    const result = await runParseTool(context, document, ['--tree']);
    const preview = await vscode.workspace.openTextDocument({
      content: result.stdout,
      language: 'plaintext',
    });
    await vscode.window.showTextDocument(preview, { preview: true, viewColumn: vscode.ViewColumn.Beside });
  } catch (error) {
    showToolError(error);
  }
}

async function runTlcCurrent(context) {
  const document = activeFlowSpecDocument();
  if (!document) {
    return;
  }
  if (document.isDirty) {
    const saved = await document.save();
    if (!saved) {
      vscode.window.showWarningMessage('Save the FlowSpec file before running TLC.');
      return;
    }
  }
  const args = ['--tlc', ...tlcBackendArgs(), document.fileName];
  await runSuiteCommand(context, args);
}

async function runSuite(context, withTlc) {
  const args = withTlc ? ['--tlc', ...tlcBackendArgs()] : [];
  await runSuiteCommand(context, args);
}

async function runSuiteCommand(context, args) {
  const root = findProjectRoot(context, vscode.window.activeTextEditor?.document);
  const module = 'flowspec.suite';
  try {
    output.clear();
    output.show(true);
    output.appendLine(`$ ${pythonPath(root)} -m ${module} ${args.join(" ")}`);
    const result = await runPythonModule(root, module, args);
    if (result.stdout) {
      output.append(result.stdout);
    }
    if (result.stderr) {
      output.append(result.stderr);
    }
    const ranTlc = args.includes('--tlc');
    vscode.window.showInformationMessage(ranTlc ? 'FlowSpec TLC run finished.' : 'FlowSpec compile suite finished.');
  } catch (error) {
    showToolError(error);
  }
}

async function validateDocument(context, document, showSuccess = false) {
  if (!isFlowSpecDocument(document)) {
    return;
  }
  try {
    const result = await runParseTool(context, document, ['--diagnostics-json'], { allowFailure: true });
    const semanticDiagnostics = diagnosticsFromJson(result.stdout);
    if (result.code !== 0 && semanticDiagnostics.length === 0) {
      diagnostics.set(document.uri, [diagnosticFromToolResult(result)]);
      if (showSuccess) {
        vscode.window.showErrorMessage('FlowSpec validation found parser errors.');
      }
      return;
    }
    diagnostics.set(document.uri, semanticDiagnostics);
    if (result.code !== 0 && semanticDiagnostics.some((diagnostic) => diagnostic.severity === vscode.DiagnosticSeverity.Error)) {
      if (showSuccess) {
        vscode.window.showErrorMessage('FlowSpec validation found errors.');
      }
      return;
    }
    if (semanticDiagnostics.length === 0) {
      diagnostics.delete(document.uri);
    }
    if (showSuccess) {
      vscode.window.showInformationMessage(
        semanticDiagnostics.length === 0 ? 'FlowSpec file is valid.' : 'FlowSpec file is valid with warnings.',
      );
    }
  } catch (error) {
    diagnostics.set(document.uri, [diagnosticFromError(error)]);
    if (showSuccess) {
      showToolError(error);
    }
  }
}

function scheduleValidation(context, document) {
  if (!isFlowSpecDocument(document)) {
    return;
  }
  const key = document.uri.toString();
  const existing = validationTimers.get(key);
  if (existing) {
    clearTimeout(existing);
  }
  validationTimers.set(key, setTimeout(() => {
    validationTimers.delete(key);
    validateDocument(context, document);
  }, 350));
}

async function runParseTool(context, document, toolArgs, options = {}) {
  const root = findProjectRoot(context, document);
  return withTempSource(document, async (sourcePath) => {
    return runPythonModule(root, 'flowspec.compiler', [...toolArgs, sourcePath], options);
  });
}

async function withTempSource(document, callback) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'flowspec-vscode-'));
  const tempPath = path.join(tempDir, path.basename(document.fileName || 'current.fspec'));
  fs.writeFileSync(tempPath, document.getText());
  try {
    return await callback(tempPath);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

function runPythonModule(root, module, args, options = {}) {
  return new Promise((resolve, reject) => {
    cp.execFile(
      pythonPath(root),
      ['-m', module, ...args],
      {
        cwd: root,
        env: { ...process.env, ...tlcEnv() },
        maxBuffer: 1024 * 1024 * 8,
      },
      (error, stdout, stderr) => {
        if (error) {
          if (options.allowFailure) {
            resolve({ stdout, stderr, code: error.code || 1 });
            return;
          }
          error.stdout = stdout;
          error.stderr = stderr;
          reject(error);
          return;
        }
        resolve({ stdout, stderr, code: 0 });
      },
    );
  });
}

function activeFlowSpecDocument() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !isFlowSpecDocument(editor.document)) {
    vscode.window.showWarningMessage('Open a .fspec file first.');
    return undefined;
  }
  return editor.document;
}

function isFlowSpecDocument(document) {
  return document && (
    document.languageId === 'flowspec'
    || document.fileName.endsWith('.fspec')
  );
}

function createCompletionProvider() {
  return {
    provideCompletionItems(document, position) {
      const linePrefix = document.lineAt(position).text.slice(0, position.character);
      const atLineStart = /^\s*\w*$/.test(linePrefix);
      const completions = [];

      if (atLineStart) {
        completions.push(...sectionSnippets());
      }

      completions.push(...keywordCompletions());
      completions.push(...contextSnippets(linePrefix));
      return completions;
    },
  };
}

function sectionSnippets() {
  return [
    snippet('Machine', 'Machine: ${1:Name}\n\nState:\n  ${2:status} is one of:\n    ${3:PENDING}\n    ${4:DONE}\n', 'Create a FlowSpec machine'),
    snippet('Given', 'Given:\n  ${1:Entity}\n', 'Add external model constants'),
    snippet('State', 'State:\n  ${1:status} is one of:\n    ${2:PENDING}\n    ${3:DONE}\n', 'Add state variables'),
    snippet('State per', 'State:\n  ${1:balance} per ${2:Account} is ${3:int}\n', 'Add entity-indexed state'),
    snippet('Initially', 'Initially:\n  ${1:status} = ${2:PENDING}\n', 'Add initial facts'),
    snippet('Move', 'Move: ${1:Name}\n  if ${2:condition}\n  then ${3:state} becomes ${4:value}\n', 'Add a move'),
    snippet('Bad state', 'Bad state: ${1:Name}\n  ${2:condition}\n', 'Add a bad state'),
    snippet('Always', 'Always: ${1:Name}\n  ${2:condition}\n', 'Add an invariant'),
    snippet('Eventually', 'Eventually: ${1:Name}\n  ${2:condition}\n', 'Add a liveness property'),
    snippet('Fairness', 'Fairness:\n  weak ${1:MoveName}\n', 'Add fairness'),
    snippet('Messages', 'Messages:\n  ${1:Event} message has:\n    type = ${1:Event}\n    ${2:id} in ${3:Ids}\n', 'Add messages or business events'),
  ];
}

function keywordCompletions() {
  const words = [
    'if',
    'then',
    'otherwise',
    'same',
    'becomes',
    'gains',
    'for some',
    'some',
    'every',
    'no',
    'has',
    'per',
    'is one of',
    'is not',
    'is in',
    'is a set of',
    'map',
    'weak',
    'strong',
    'nat',
    'int',
  ];
  return words.map((word) => {
    const item = new vscode.CompletionItem(word, vscode.CompletionItemKind.Keyword);
    item.insertText = word;
    return item;
  });
}

function contextSnippets(linePrefix) {
  const completions = [];
  if (/^\s*then\s+\w*\s*$/.test(linePrefix)) {
    completions.push(snippet('becomes', 'becomes ${1:value}', 'Change state in a move'));
    completions.push(snippet('gains', 'gains ${1:item}', 'Add item to a set-valued state'));
  }
  if (/^\s*for\s*$/.test(linePrefix)) {
    completions.push(snippet('some', 'some ${1:item} in ${2:Items}', 'Choose one item from a set'));
  }
  if (/^\s*\w+\s*$/.test(linePrefix)) {
    completions.push(snippet('per', 'per ${1:Entity} is ${2:int}', 'One value per business entity'));
    completions.push(snippet('is one of', 'is one of:\n  ${1:PENDING}\n  ${2:DONE}', 'Enum state type'));
  }
  return completions;
}

function snippet(label, body, detail) {
  const item = new vscode.CompletionItem(label, vscode.CompletionItemKind.Snippet);
  item.insertText = new vscode.SnippetString(body);
  item.detail = detail;
  return item;
}

function updateStatusItem() {
  const document = vscode.window.activeTextEditor?.document;
  if (isFlowSpecDocument(document)) {
    statusItem.show();
  } else {
    statusItem.hide();
  }
}

function findProjectRoot(context, document) {
  const configured = configValue('projectRoot', '');
  if (configured) {
    return configured;
  }

  const candidates = [];
  if (document && document.uri.scheme === 'file') {
    candidates.push(...parents(path.dirname(document.fileName)));
  }
  for (const folder of vscode.workspace.workspaceFolders || []) {
    candidates.push(folder.uri.fsPath);
  }
  candidates.push(path.resolve(context.extensionPath, '..'));

  const root = candidates.find((candidate) => fs.existsSync(path.join(candidate, 'flowspec', 'compiler.py')));
  if (root) {
    return root;
  }

  if (document && document.uri.scheme === 'file') {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    return workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(document.fileName);
  }

  if (vscode.workspace.workspaceFolders?.length) {
    return vscode.workspace.workspaceFolders[0].uri.fsPath;
  }

  throw new Error('Could not choose a FlowSpec working directory. Open a folder or set flowspec.projectRoot in VS Code settings.');
}

function parents(start) {
  const result = [];
  let current = start;
  while (current && current !== path.dirname(current)) {
    result.push(current);
    current = path.dirname(current);
  }
  return result;
}

function pythonPath(root) {
  const configured = configValue('pythonPath', '');
  if (configured) {
    return configured;
  }
  const venvPython = path.join(root, '.venv', 'bin', 'python');
  return fs.existsSync(venvPython) ? venvPython : 'python3';
}

function tlcBackendArgs() {
  const backend = configValue('tlcBackend', 'docker');
  const args = ['--tlc-backend', backend];
  if (backend === 'docker') {
    args.push('--tlc-image', configValue('tlcImage', 'ghcr.io/mohamed-elfiky/flowspec-tlc:0.0.1'));
  } else if (configValue('tlcJar', '')) {
    args.push('--tlc-jar', configValue('tlcJar', ''));
  }
  return args;
}

function tlcEnv() {
  const env = {};
  if (configValue('tlcImage', '')) {
    env.FLOWSPEC_TLC_IMAGE = configValue('tlcImage', '');
  }
  if (configValue('tlcJar', '')) {
    env.FLOWSPEC_TLC_JAR = configValue('tlcJar', '');
  }
  return env;
}

function configValue(key, fallback) {
  const next = vscode.workspace.getConfiguration('flowspec').get(key);
  return next === undefined || next === '' ? fallback : next;
}

function diagnosticFromError(error) {
  const text = `${error.stderr || ''}\n${error.stdout || ''}`;
  const match = text.match(/line\s+(\d+),\s+column\s+(\d+)/i);
  const line = match ? Math.max(Number(match[1]) - 1, 0) : 0;
  const character = match ? Math.max(Number(match[2]) - 1, 0) : 0;
  const range = new vscode.Range(line, character, line, character + 1);
  return new vscode.Diagnostic(range, shortErrorMessage(text), vscode.DiagnosticSeverity.Error);
}

function diagnosticFromToolResult(result) {
  const text = `${result.stderr || ''}\n${result.stdout || ''}`;
  const match = text.match(/line\s+(\d+),\s+column\s+(\d+)/i);
  const line = match ? Math.max(Number(match[1]) - 1, 0) : 0;
  const character = match ? Math.max(Number(match[2]) - 1, 0) : 0;
  const range = new vscode.Range(line, character, line, character + 1);
  return new vscode.Diagnostic(range, shortErrorMessage(text), vscode.DiagnosticSeverity.Error);
}

function diagnosticsFromJson(stdout) {
  let raw;
  try {
    raw = JSON.parse(stdout || '[]');
  } catch {
    return [];
  }
  return raw.map((item) => {
    const line = Math.max(Number(item.line) || 0, 0);
    const column = Math.max(Number(item.column) || 0, 0);
    const range = new vscode.Range(line, column, line, column + 1);
    const severity = item.severity === 'warning'
      ? vscode.DiagnosticSeverity.Warning
      : vscode.DiagnosticSeverity.Error;
    return new vscode.Diagnostic(range, item.message || 'FlowSpec diagnostic', severity);
  });
}

function shortErrorMessage(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const useful = lines.find((line) => line.startsWith('Unexpected') || line.startsWith('No terminal') || line.startsWith('Expected'));
  return useful || lines[0] || 'FlowSpec validation failed.';
}

function showToolError(error) {
  output.show(true);
  if (error.stdout) {
    output.append(error.stdout);
  }
  if (error.stderr) {
    output.append(error.stderr);
  }
  vscode.window.showErrorMessage(shortErrorMessage(`${error.stderr || ''}\n${error.stdout || ''}`));
}

module.exports = {
  activate,
  deactivate,
};
