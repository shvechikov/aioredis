import sys
import unittest
import asyncio
from textwrap import dedent

from ._testutil import RedisTest, run_until_complete, REDIS_VERSION


PY_35 = sys.version_info > (3, 5)


class PubSubCommandsTest(RedisTest):

    @asyncio.coroutine
    def _reader(self, channel, output, waiter, conn=None):
        if conn is None:
            conn = yield from self.create_connection(
                ('localhost', self.redis_port), loop=self.loop)
        yield from conn.execute('subscribe', channel)
        ch = conn.pubsub_channels[channel]
        waiter.set_result(conn)
        while (yield from ch.wait_message()):
            msg = yield from ch.get()
            yield from output.put(msg)

    @run_until_complete
    def test_publish(self):
        out = asyncio.Queue(loop=self.loop)
        fut = asyncio.Future(loop=self.loop)
        sub = asyncio.async(self._reader('chan:1', out, fut),
                            loop=self.loop)

        redis = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        yield from fut
        yield from redis.publish('chan:1', 'Hello')
        msg = yield from out.get()
        self.assertEqual(msg, b'Hello')

        sub.cancel()

    @run_until_complete
    def test_publish_json(self):
        out = asyncio.Queue(loop=self.loop)
        fut = asyncio.Future(loop=self.loop)
        sub = asyncio.async(self._reader('chan:1', out, fut),
                            loop=self.loop)

        redis = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        yield from fut

        res = yield from redis.publish_json('chan:1', {"Hello": "world"})
        self.assertEqual(res, 1)    # recievers

        msg = yield from out.get()
        self.assertEqual(msg, b'{"Hello": "world"}')
        sub.cancel()

    @run_until_complete
    def test_subscribe(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        res = yield from sub.subscribe('chan:1', 'chan:2')
        self.assertEqual(sub.in_pubsub, 2)

        ch1 = sub.channels['chan:1']
        ch2 = sub.channels['chan:2']

        self.assertEqual(res, [ch1, ch2])
        self.assertFalse(ch1.is_pattern)
        self.assertFalse(ch2.is_pattern)

        res = yield from sub.unsubscribe('chan:1', 'chan:2')
        self.assertEqual(res, [[b'unsubscribe', b'chan:1', 1],
                               [b'unsubscribe', b'chan:2', 0]])

    @run_until_complete
    def test_psubscribe(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        res = yield from sub.psubscribe('patt:*', 'chan:*')
        self.assertEqual(sub.in_pubsub, 2)

        pat1 = sub.patterns['patt:*']
        pat2 = sub.patterns['chan:*']
        self.assertEqual(res, [pat1, pat2])

        pub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        yield from pub.publish_json('chan:123', {"Hello": "World"})
        res = yield from pat2.get_json()
        self.assertEqual(res, (b'chan:123', {"Hello": "World"}))

        res = yield from sub.punsubscribe('patt:*', 'patt:*', 'chan:*')
        self.assertEqual(res, [[b'punsubscribe', b'patt:*', 1],
                               [b'punsubscribe', b'patt:*', 1],
                               [b'punsubscribe', b'chan:*', 0],
                               ])

    @unittest.skipIf(REDIS_VERSION < (2, 8, 0),
                     'PUBSUB CHANNELS is available since redis>=2.8.0')
    @run_until_complete
    def test_pubsub_channels(self):
        redis = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        res = yield from redis.pubsub_channels()
        self.assertEqual(res, [])

        res = yield from redis.pubsub_channels('chan:*')
        self.assertEqual(res, [])

        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        yield from sub.subscribe('chan:1')

        res = yield from redis.pubsub_channels()
        self.assertEqual(res, [b'chan:1'])

        res = yield from redis.pubsub_channels('ch*')
        self.assertEqual(res, [b'chan:1'])

        yield from sub.unsubscribe('chan:1')
        yield from sub.psubscribe('chan:*')

        res = yield from redis.pubsub_channels()
        self.assertEqual(res, [])

    @unittest.skipIf(REDIS_VERSION < (2, 8, 0),
                     'PUBSUB NUMSUB is available since redis>=2.8.0')
    @run_until_complete
    def test_pubsub_numsub(self):
        redis = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        res = yield from redis.pubsub_numsub()
        self.assertEqual(res, {})

        res = yield from redis.pubsub_numsub('chan:1')
        self.assertEqual(res, {b'chan:1': 0})

        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        yield from sub.subscribe('chan:1')

        res = yield from redis.pubsub_numsub()
        self.assertEqual(res, {})

        res = yield from redis.pubsub_numsub('chan:1')
        self.assertEqual(res, {b'chan:1': 1})

        res = yield from redis.pubsub_numsub('chan:2')
        self.assertEqual(res, {b'chan:2': 0})

        res = yield from redis.pubsub_numsub('chan:1', 'chan:2')
        self.assertEqual(res, {b'chan:1': 1, b'chan:2': 0})

        yield from sub.unsubscribe('chan:1')
        yield from sub.psubscribe('chan:*')

        res = yield from redis.pubsub_numsub()
        self.assertEqual(res, {})

    @unittest.skipIf(REDIS_VERSION < (2, 8, 0),
                     'PUBSUB NUMPAT is available since redis>=2.8.0')
    @run_until_complete
    def test_pubsub_numpat(self):
        redis = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        res = yield from redis.pubsub_numpat()
        self.assertEqual(res, 0)

        yield from sub.subscribe('chan:1')
        res = yield from redis.pubsub_numpat()
        self.assertEqual(res, 0)

        yield from sub.psubscribe('chan:*')
        res = yield from redis.pubsub_numpat()
        self.assertEqual(res, 1)

    @run_until_complete
    def test_close_pubsub_channels(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        ch, = yield from sub.subscribe('chan:1')

        @asyncio.coroutine
        def waiter(ch):
            msg = _empty = object()
            while (yield from ch.wait_message()):
                msg = yield from ch.get()
            # assert no ``ch.get()`` call
            self.assertIs(msg, _empty)

        tsk = asyncio.async(waiter(ch), loop=self.loop)
        sub.close()
        yield from sub.wait_closed()
        yield from tsk

    @run_until_complete
    def test_close_pubsub_patterns(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        ch, = yield from sub.psubscribe('chan:*')

        @asyncio.coroutine
        def waiter(ch):
            msg = _empty = object()
            while (yield from ch.wait_message()):
                msg = yield from ch.get()
            # assert no ``ch.get()`` call
            self.assertIs(msg, _empty)

        tsk = asyncio.async(waiter(ch), loop=self.loop)
        sub.close()
        yield from sub.wait_closed()
        yield from tsk

    @run_until_complete
    def test_close_cancelled_pubsub_channel(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        ch, = yield from sub.subscribe('chan:1')

        @asyncio.coroutine
        def waiter(ch):
            with self.assertRaises(asyncio.CancelledError):
                while (yield from ch.wait_message()):
                    yield from ch.get()

        tsk = asyncio.async(waiter(ch), loop=self.loop)
        yield from asyncio.sleep(0, loop=self.loop)
        tsk.cancel()
        sub.close()
        yield from sub.wait_closed()

    @run_until_complete
    def test_channel_get_after_close(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        pub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        ch, = yield from sub.subscribe('chan:1')

        @asyncio.coroutine
        def waiter():
            while True:
                msg = yield from ch.get()
                if msg is None:
                    break
                self.assertEqual(msg, b'message')

        tsk = asyncio.async(waiter(), loop=self.loop)

        yield from pub.publish('chan:1', 'message')
        sub.close()
        yield from tsk

    @unittest.skipUnless(PY_35, "Python 3.5+ required")
    @run_until_complete
    def test_pubsub_channel_iter(self):
        sub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)
        pub = yield from self.create_redis(
            ('localhost', self.redis_port), loop=self.loop)

        ch, = yield from sub.subscribe('chan:1')

        s = dedent('''\
        async def coro(ch):
            lst = []
            async for msg in ch.iter():
                lst.append(msg)
            return lst
        ''')
        lcl = {}
        exec(s, globals(), lcl)
        coro = lcl['coro']

        tsk = asyncio.async(coro(ch), loop=self.loop)
        yield from pub.publish_json('chan:1', {'Hello': 'World'})
        yield from pub.publish_json('chan:1', ['message'])
        yield from asyncio.sleep(0, loop=self.loop)
        ch.close()
        lst = yield from tsk
        self.assertEqual(lst, [
            b'{"Hello": "World"}',
            b'["message"]',
            ])
