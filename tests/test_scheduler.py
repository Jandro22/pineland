import unittest

from pineland_sim.events import EventScheduler


class SchedulerTests(unittest.TestCase):
    def test_orders_by_time_priority_then_insertion(self):
        scheduler = EventScheduler()
        scheduler.schedule(2, "late")
        scheduler.schedule(1, "second", priority=20)
        scheduler.schedule(1, "first", priority=10)
        self.assertEqual([scheduler.pop_next().event_type for _ in range(3)], ["first", "second", "late"])


if __name__ == "__main__":
    unittest.main()

