import unittest

from nightfall import telemetry


class TelemetryOffTests(unittest.TestCase):
    """With nothing configured, telemetry has to be invisible and free."""

    def test_no_exporter_means_no_providers_to_shut_down(self):
        self.assertEqual(telemetry._PROVIDERS, [])

    def test_span_is_a_context_manager_that_returns_a_span(self):
        with telemetry.span("test.span", a=1) as span:
            span.set_attribute("b", 2)
            span.add_event("c", {"d": 3})
            span.set_status("ok")

    def test_span_does_not_swallow_the_bodies_exception(self):
        # The one bug that matters here: a telemetry wrapper that eats the
        # caller's error would turn every failure into a silent success.
        with self.assertRaises(ZeroDivisionError), telemetry.span("test.span"):
            _ = 1 / 0

    def test_span_passes_the_body_through_to_the_caller(self):
        with telemetry.span("test.span") as span:
            return span

    def test_count_ignores_missing_and_fake_numbers(self):
        telemetry.count(telemetry.tokens, None)
        telemetry.count(telemetry.tokens, 0)
        telemetry.count(telemetry.errors, 1, {"kind": "tool", "tool": "bash"})

    def test_shutdown_without_providers_is_a_no_op(self):
        telemetry.shutdown()

    def test_instruments_exist_even_when_off(self):
        instruments = (
            telemetry.turns,
            telemetry.tool_calls,
            telemetry.tokens,
            telemetry.errors,
        )
        for instrument in instruments:
            instrument.add(1, {})


if __name__ == "__main__":
    unittest.main()
