import math
import random
import time


class MockDynoSource:
    """
    Fake shock dyno data source.

    This lets the GUI behave like real dyno hardware exists,
    even before the Teensy, sensors, and frame are finished.
    """

    def __init__(self):
        self.simulation_start_time = time.time()

    def reset(self):
        self.simulation_start_time = time.time()

    def get_sample(self, stroke_in: float, rpm: float, test_start_time) -> dict:
        now = time.time()
        elapsed = now - self.simulation_start_time

        crank_radius_in = stroke_in / 2.0
        frequency_hz = rpm / 60.0
        omega = 2.0 * math.pi * frequency_hz

        position_centered_in = crank_radius_in * math.sin(omega * elapsed)
        velocity_in_s = crank_radius_in * omega * math.cos(omega * elapsed)

        position_in = position_centered_in + crank_radius_in

        damping_lbf_per_in_s = 25.0
        spring_effect_lbf_per_in = 8.0

        force_lbf = (
            damping_lbf_per_in_s * velocity_in_s
            + spring_effect_lbf_per_in * position_centered_in
        )

        force_lbf += random.uniform(-2.0, 2.0)
        position_in += random.uniform(-0.005, 0.005)

        if test_start_time is None:
            time_s = 0.0
        else:
            time_s = now - test_start_time

        return {
            "time_s": round(time_s, 6),
            "force_lbf": round(force_lbf, 3),
            "position_in": round(position_in, 4),
            "velocity_in_s": round(velocity_in_s, 4),
        }