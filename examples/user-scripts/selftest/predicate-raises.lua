-- Expected: "FAIL selftest/predicate-raises: waitFor predicate raised: ...attempt to index
-- local 'group' (a nil value)". Other runs (e.g. long-run) keep going.
Hotload.waitFor(function()
  local group = Group.getByName("no-such-group-hotload-selftest")
  return group:isExist()
end, 5)
return "unreachable"
