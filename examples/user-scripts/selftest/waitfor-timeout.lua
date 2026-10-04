-- Expected: "done selftest/waitfor-timeout (3.1s) -> false". A timeout is not an error.
return Hotload.waitFor(function()
  return false
end, 3)
