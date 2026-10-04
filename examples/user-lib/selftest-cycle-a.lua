-- Loads b, which loads a: a cycle. Hotload.load must refuse it.
Hotload.load("selftest-cycle-b")
return {}
