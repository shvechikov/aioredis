import asyncio

from ._testutil import BaseTest, run_until_complete


class TaskCancellationTest(BaseTest):

    @run_until_complete
    def test_future_cancellation(self):
        conn = yield from self.create_connection(
            ('localhost', 6379), loop=self.loop)

        ts = self.loop.time()
        fut = conn.execute('BLPOP', 'some-list', 5)
        try:
            yield from asyncio.wait_for(fut, 1, loop=self.loop)
        except asyncio.TimeoutError:
            pass
        self.assertTrue(fut.cancelled())

        # XXX: Connection becomes available only after timeout expires
        yield from conn.execute('TIME')
        dt = int(self.loop.time() - ts)
        self.assertAlmostEqual(dt, 5, places=5)
