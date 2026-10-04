-- Expected: "FAIL selftest/runtime-error: ...attempt to index local 'missing' (a nil value)",
-- followed in dcs.log by a stack traceback naming this file.
local missing = nil
return missing.field
