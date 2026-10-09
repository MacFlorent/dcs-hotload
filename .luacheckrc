-- luacheck configuration, read by .github/scripts/lint.sh, locally and in CI.
std = "lua51"
max_line_length = 120

-- examples/ holds deliberately broken self-tests (a syntax error, a runtime error); luaunit is
-- vendored as published; dist/ is the release package a local package.sh run leaves behind.
exclude_files = { "examples/**", "test/luaunit.lua", "dist/**" }

files["dcs-hotload.lua"] = {
  globals = { "Hotload", "HotloadCore" },                         -- the two it writes
  read_globals = { "env", "timer", "trigger", "missionCommands", "lfs" },
}

files["test/**"] = {
  -- The stub installs the DCS globals and each suite declares its luaunit tables globally.
  globals = { "Hotload", "HotloadCore", "env", "timer", "trigger", "missionCommands", "io", "debug" },
  read_globals = { "lfs" },
  allow_defined_top = true,
  self = false,                                                  -- luaunit's method style
}
