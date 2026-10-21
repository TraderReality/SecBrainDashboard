import unittest

from loop.watcher_loop_runtime import WatcherLoopRuntime


class WatcherLoopRuntimeTest(unittest.TestCase):
    def test_model_starts_at_first_station_and_advances_only_on_success(self):
        runtime = WatcherLoopRuntime()
        runtime.start("qwen3:14b")
        self.assertEqual(runtime.status()["current_station"], 1)

        request = runtime.begin("qwen3:14b")
        transition = runtime.complete(request, "Analyse abgeschlossen")

        self.assertEqual(transition["completed_station"], 1)
        self.assertEqual(transition["next_station"], 2)
        self.assertEqual(runtime.status()["current_station"], 2)
        self.assertIn("Ausgabe: Analyse abgeschlossen", runtime.status()["events"][-1]["message"])

    def test_failure_keeps_the_station_active(self):
        runtime = WatcherLoopRuntime()
        runtime.start("qwen3:14b")
        request = runtime.begin("qwen3:14b")
        runtime.fail(request, "Ollama nicht erreichbar")

        state = runtime.status()
        self.assertEqual(state["current_station"], 1)
        self.assertFalse(state["busy"])

    def test_parallel_execution_is_rejected(self):
        runtime = WatcherLoopRuntime()
        runtime.start("qwen3:14b")
        runtime.begin("qwen3:14b")

        with self.assertRaises(RuntimeError):
            runtime.begin("qwen3:14b")

    def test_only_the_active_model_can_advance_the_run(self):
        runtime = WatcherLoopRuntime()
        runtime.start("qwen3:14b")

        with self.assertRaises(ValueError):
            runtime.begin("another-model")

    def test_external_proposal_can_start_directly_at_approval(self):
        runtime = WatcherLoopRuntime()
        runtime.start_at("qwen3:14b", 6, "Radar-Vorschlag übergeben.")
        state = runtime.status()
        self.assertEqual(state["current_station"], 6)
        self.assertTrue(state["readonly"])
        self.assertEqual(state["events"][-1]["event"], "run_handed_off")


if __name__ == "__main__":
    unittest.main()
