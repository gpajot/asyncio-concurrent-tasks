from tasktools.threaded_pool.blocking import BlockingThreadedTaskPool


def test_methods(sleep):
    with BlockingThreadedTaskPool() as pool:
        assert pool.create_task(sleep(0.01)).result() == 0.01
        assert pool.run(sleep(0.01)) == 0.01
