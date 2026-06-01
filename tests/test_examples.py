from pathlib import Path
import unittest

from flowspec.backends.tla import compile_tla
from flowspec.narrator import narrate_tlc_failure
from flowspec.parser import build_parser, parse_spec
from flowspec.validator import semantic_diagnostics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = [
    PROJECT_ROOT / "examples" / "transaction.fspec",
    PROJECT_ROOT / "examples" / "account.fspec",
    PROJECT_ROOT / "examples" / "payment.fspec",
    PROJECT_ROOT / "examples" / "wallet_topup.fspec",
    PROJECT_ROOT / "examples" / "2pc.fspec",
]

TUTORIAL_EXAMPLES = [
    PROJECT_ROOT / "examples" / "tutorial" / "deceptive_double_post_bad.fspec",
    PROJECT_ROOT / "examples" / "tutorial" / "deceptive_double_post_fixed.fspec",
]

CAPABILITY_EXAMPLES = [
    PROJECT_ROOT / "examples" / "capability" / "progress_billing.fspec",
]


class ExampleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = build_parser()

    def compile_example(self, source_path: Path) -> str:
        tree = self.parser.parse(source_path.read_text())
        spec = parse_spec(tree)
        diagnostics = semantic_diagnostics(spec)
        errors = [diagnostic for diagnostic in diagnostics if diagnostic.severity == "error"]
        self.assertEqual(errors, [], f"{source_path} has semantic errors: {errors}")
        return compile_tla(spec)

    def test_supported_examples_compile_and_validate(self):
        for source_path in EXAMPLES:
            with self.subTest(example=source_path.name):
                tla = self.compile_example(source_path)
                self.assertIn("---- MODULE ", tla)
                self.assertIn("Spec ==", tla)
                self.assertIn("Init ==", tla)
                self.assertIn("Next ==", tla)
                self.assertTrue(tla.endswith("====\n"))

    def test_tutorial_examples_compile_and_validate(self):
        for source_path in TUTORIAL_EXAMPLES:
            with self.subTest(example=source_path.name):
                tla = self.compile_example(source_path)
                self.assertIn("---- MODULE DeceptiveDoublePost", tla)
                self.assertIn("NoOverdraft ==", tla)
                self.assertIn("NoDoublePosted ==", tla)

    def test_capability_examples_compile_and_validate(self):
        for source_path in CAPABILITY_EXAMPLES:
            with self.subTest(example=source_path.name):
                tla = self.compile_example(source_path)
                self.assertIn("---- MODULE ProgressBilling ----", tla)
                self.assertIn("projectStatus \\in [Project ->", tla)
                self.assertIn("NoRevenueExceedsContract ==", tla)
                self.assertIn("ClosedMeansFullyCollected ==", tla)
                self.assertIn("FinalRevenueWithoutAcceptance ==", tla)

    def test_payment_generates_business_invariants(self):
        tla = self.compile_example(PROJECT_ROOT / "examples" / "payment.fspec")

        self.assertIn('status \\in {"PENDING", "POSTED", "REJECTED"}', tla)
        self.assertIn("sourceBalance' = sourceBalance - amount", tla)
        self.assertIn("destinationBalance' = destinationBalance + amount", tla)
        self.assertIn("NoOverdraft ==", tla)
        self.assertIn("~(Overdraft)", tla)

    def test_wallet_topup_models_unknown_polling_and_reversal(self):
        tla = self.compile_example(PROJECT_ROOT / "examples" / "wallet_topup.fspec")

        self.assertIn("---- MODULE WalletTopup ----", tla)
        self.assertIn("TopupResultUnknown ==", tla)
        self.assertIn("PollDetailsCompleted ==", tla)
        self.assertIn("ReconcileTopupReverse ==", tla)
        self.assertIn("reconEvents \\in SUBSET Messages", tla)
        self.assertIn("TopupReverse(request) \\in reconEvents", tla)
        self.assertIn("NoReverseWithoutTopup ==", tla)
        self.assertIn("walletBalance' = [walletBalance EXCEPT ![MerchantWallet]", tla)
        self.assertEqual(tla.count("walletBalance' = [walletBalance EXCEPT"), 3)

    def test_account_generates_per_entity_state(self):
        tla = self.compile_example(PROJECT_ROOT / "examples" / "account.fspec")

        self.assertIn("CONSTANTS Account", tla)
        self.assertIn("balance \\in [Account -> {0}]", tla)
        self.assertIn("balance = [account \\in Account |-> 0]", tla)

    def test_two_phase_commit_generates_function_updates(self):
        tla = self.compile_example(PROJECT_ROOT / "examples" / "2pc.fspec")

        self.assertIn('rmState \\in [RM -> {"working", "prepared", "committed", "aborted"}]', tla)
        self.assertIn('rmState\' = [rmState EXCEPT ![r] = "prepared"]', tla)
        self.assertIn('rmState\' = [rmState EXCEPT ![r] = "committed"]', tla)
        self.assertNotIn("rmState'[r]", tla)

    def test_trace_mode_instruments_moves_without_affecting_default_tla(self):
        source_path = PROJECT_ROOT / "examples" / "payment.fspec"
        tree = self.parser.parse(source_path.read_text())
        spec = parse_spec(tree)

        normal_tla = compile_tla(spec)
        trace_tla = compile_tla(spec, trace=True)

        self.assertNotIn("__flowMove", normal_tla)
        self.assertIn("VARIABLES status, amount, sourceBalance, destinationBalance, __flowMove", trace_tla)
        self.assertIn('__flowMove = "Init"', trace_tla)
        self.assertIn('__flowMove\' = "Post"', trace_tla)

    def test_tlc_narrator_maps_trace_moves_to_flowspec_source(self):
        source_path = PROJECT_ROOT / "examples" / "tutorial" / "deceptive_double_post_bad.fspec"
        tree = self.parser.parse(source_path.read_text())
        spec = parse_spec(tree)
        output = """
Error: Invariant NoDoublePosted is violated.
State 1: <Initial predicate>
/\\ status = "PENDING"
/\\ destinationBalance = 0
/\\ __flowMove = "Init"

State 2: <WorkerReadsPending line 20>
/\\ status = "PENDING"
/\\ destinationBalance = 0
/\\ __flowMove = "WorkerReadsPending"

State 3: <WorkerPostsFromAttempt line 25>
/\\ status = "POSTED"
/\\ destinationBalance = 120
/\\ __flowMove = "WorkerPostsFromAttempt"
"""

        narration = narrate_tlc_failure(output, spec, source_path)

        self.assertIsNotNone(narration)
        self.assertIn("Property violated: NoDoublePosted [bad state]", narration)
        self.assertIn("Property source:", narration)
        self.assertIn("Bad state: DoublePosted", narration)
        self.assertIn("1. WorkerReadsPending", narration)
        self.assertIn("2. WorkerPostsFromAttempt", narration)
        self.assertIn("Move source:", narration)
        self.assertIn("Move: WorkerPostsFromAttempt", narration)
        self.assertIn('destinationBalance = 120', narration)

    def test_example_output_fixtures_document_narrated_tlc_results(self):
        bad_output = (PROJECT_ROOT / "examples" / "tutorial" / "deceptive_double_post_bad.out.txt").read_text()
        billing_output = (PROJECT_ROOT / "examples" / "capability" / "progress_billing.out.txt").read_text()

        self.assertIn("flowspec-suite --tlc --tlc-narrate", bad_output)
        self.assertIn("Property source:", bad_output)
        self.assertIn("Move source:", bad_output)
        self.assertIn("WorkerPostsFromAttempt", bad_output)
        self.assertIn("repeated", bad_output)
        self.assertIn("PASS TLC ProgressBilling", billing_output)


if __name__ == "__main__":
    unittest.main()
