"""Generates train.json and heldout.json. Run: python build_tasks.py

Train tasks: lanes see prompts + per-test pass/fail (test name and what they returned).
Heldout tasks: lanes never see them. Final score comes only from these.
Each task has traps a naive one-shot solution tends to miss (see test names).
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def eq(name, expr, expected):
    return {"name": name, "code": f"_r = {expr}\nassert _r == {expected!r}, f'got {{_r!r}}'"}


def approx(name, expr, expected):
    return {"name": name, "code": f"_r = {expr}\nassert abs(_r - {expected!r}) < 1e-9, f'got {{_r!r}}'"}


def raises(name, expr, exc="ValueError"):
    return {"name": name, "code": f"try:\n    _r = {expr}\nexcept {exc}:\n    pass\n"
                                  f"else:\n    raise AssertionError(f'expected {exc}, got {{_r!r}}')"}


def check(name, code):
    return {"name": name, "code": code}


TRAIN = [
    {"id": "roman_to_int", "entry": "roman_to_int", "prompt":
     "Write `roman_to_int(s: str) -> int` converting an uppercase Roman numeral (1..3999) to an int. "
     "Raise ValueError for anything that is not the canonical numeral: empty string, lowercase, invalid "
     "characters, or non-canonical forms such as 'IIII', 'IC', 'VX'.",
     "tests": [eq("basic", "roman_to_int('III')", 3), eq("mixed", "roman_to_int('LVIII')", 58),
               eq("subtractive", "roman_to_int('MCMXCIV')", 1994), eq("max", "roman_to_int('MMMCMXCIX')", 3999),
               raises("rejects_IIII", "roman_to_int('IIII')"), raises("rejects_IC", "roman_to_int('IC')"),
               raises("rejects_empty", "roman_to_int('')"), raises("rejects_lowercase", "roman_to_int('mcm')")]},

    {"id": "parse_duration", "entry": "parse_duration", "prompt":
     "Write `parse_duration(s: str) -> int` returning total seconds. Input is one or more `<int><unit>` parts "
     "with units d, h, m, s, appearing in that order, each at most once, no spaces, e.g. '1h30m', '2d', "
     "'1d2h3m4s'. Raise ValueError for anything else (empty, repeated or out-of-order units, decimals, "
     "missing number or unit, spaces).",
     "tests": [eq("hours_minutes", "parse_duration('1h30m')", 5400), eq("seconds_only", "parse_duration('90s')", 90),
               eq("days", "parse_duration('2d')", 172800), eq("all_units", "parse_duration('1d2h3m4s')", 93784),
               eq("zero", "parse_duration('0s')", 0), raises("rejects_empty", "parse_duration('')"),
               raises("rejects_repeated_unit", "parse_duration('1h1h')"),
               raises("rejects_out_of_order", "parse_duration('30m1h')"),
               raises("rejects_decimal", "parse_duration('1.5h')"), raises("rejects_missing_number", "parse_duration('h')"),
               raises("rejects_missing_unit", "parse_duration('10')"), raises("rejects_space", "parse_duration('1 h')")]},

    {"id": "merge_intervals", "entry": "merge_intervals", "prompt":
     "Write `merge_intervals(intervals: list[list[int]]) -> list[list[int]]`. Merge overlapping intervals and "
     "intervals that touch (end == next start). Return them sorted by start. Do not mutate the input.",
     "tests": [eq("classic", "merge_intervals([[1,3],[2,6],[8,10],[15,18]])", [[1, 6], [8, 10], [15, 18]]),
               eq("touching_merge", "merge_intervals([[1,4],[4,5]])", [[1, 5]]),
               eq("unsorted_input", "merge_intervals([[5,6],[1,2]])", [[1, 2], [5, 6]]),
               eq("contained", "merge_intervals([[1,10],[2,3]])", [[1, 10]]),
               eq("empty", "merge_intervals([])", []),
               check("does_not_mutate_input", "x = [[3,4],[1,2]]\nmerge_intervals(x)\nassert x == [[3,4],[1,2]], f'input became {x!r}'")]},

    {"id": "eval_rpn", "entry": "eval_rpn", "prompt":
     "Write `eval_rpn(tokens: list[str]) -> int` evaluating integer Reverse Polish Notation with + - * /. "
     "Division truncates toward zero. Raise ValueError for malformed input (empty, too few operands, "
     "leftover operands). Division by zero raises ZeroDivisionError.",
     "tests": [eq("basic", "eval_rpn(['2','1','+','3','*'])", 9), eq("division", "eval_rpn(['4','13','5','/','+'])", 6),
               eq("negative_division_truncates_toward_zero", "eval_rpn(['-7','2','/'])", -3),
               eq("negative_divisor_truncates_toward_zero", "eval_rpn(['7','-2','/'])", -3),
               raises("rejects_too_few_operands", "eval_rpn(['1','+'])"),
               raises("rejects_leftover_operands", "eval_rpn(['1','2'])"), raises("rejects_empty", "eval_rpn([])"),
               raises("division_by_zero", "eval_rpn(['1','0','/'])", "ZeroDivisionError")]},

    {"id": "wrap_text", "entry": "wrap_text", "prompt":
     "Write `wrap_text(text: str, width: int) -> list[str]`. Split on any whitespace, then greedily pack words "
     "into lines joined by single spaces, each line at most `width` characters. A word longer than `width` "
     "starts on a new line (if the current line is non-empty) and is cut into `width`-sized pieces; its last "
     "piece stays open so following words can join it. Empty or whitespace-only text returns []. "
     "Raise ValueError if width < 1.",
     "tests": [eq("basic", "wrap_text('the quick brown fox', 10)", ["the quick", "brown fox"]),
               eq("width_one", "wrap_text('a b c', 1)", ["a", "b", "c"]),
               eq("long_word_split", "wrap_text('abcdefghij', 4)", ["abcd", "efgh", "ij"]),
               eq("long_word_tail_joins_next", "wrap_text('hi abcdefghij x', 4)", ["hi", "abcd", "efgh", "ij x"]),
               eq("collapses_whitespace", "wrap_text('  lots   of\\n\\nspace ', 20)", ["lots of space"]),
               eq("empty", "wrap_text('', 5)", []), raises("rejects_zero_width", "wrap_text('a', 0)")]},

    {"id": "semver_compare", "entry": "semver_compare", "prompt":
     "Write `semver_compare(a: str, b: str) -> int` returning -1, 0 or 1 by Semantic Versioning 2.0.0 "
     "precedence: MAJOR.MINOR.PATCH, optional -prerelease, optional +build (ignored). A prerelease is lower "
     "than the release. Prerelease identifiers compare left to right: numeric ones numerically, others "
     "lexically in ASCII, numeric lower than alphanumeric, and a shorter identifier list is lower when all "
     "preceding identifiers are equal. Raise ValueError for invalid versions (missing parts, leading zeros "
     "in numeric parts).",
     "tests": [eq("major", "semver_compare('1.0.0','2.0.0')", -1), eq("minor_beats_patch", "semver_compare('2.1.0','2.0.9')", 1),
               eq("numeric_not_lexical", "semver_compare('1.10.0','1.9.0')", 1),
               eq("prerelease_below_release", "semver_compare('1.0.0-alpha','1.0.0')", -1),
               eq("shorter_prerelease_lower", "semver_compare('1.0.0-alpha','1.0.0-alpha.1')", -1),
               eq("numeric_below_alnum", "semver_compare('1.0.0-alpha.1','1.0.0-alpha.beta')", -1),
               eq("prerelease_numeric_compare", "semver_compare('1.0.0-beta.2','1.0.0-beta.11')", -1),
               eq("prerelease_lexical_compare", "semver_compare('1.0.0-rc.1','1.0.0-beta.11')", 1),
               eq("build_ignored", "semver_compare('1.0.0+build.5','1.0.0+other')", 0),
               raises("rejects_missing_patch", "semver_compare('1.0','1.0.0')"),
               raises("rejects_leading_zero", "semver_compare('01.0.0','1.0.0')")]},
]

HELDOUT = [
    {"id": "int_to_roman", "entry": "int_to_roman", "prompt":
     "Write `int_to_roman(n: int) -> str` returning the canonical uppercase Roman numeral for 1..3999. "
     "Raise ValueError outside that range.",
     "tests": [eq("three", "int_to_roman(3)", "III"), eq("four", "int_to_roman(4)", "IV"), eq("nine", "int_to_roman(9)", "IX"),
               eq("mixed", "int_to_roman(58)", "LVIII"), eq("subtractive", "int_to_roman(1994)", "MCMXCIV"),
               eq("max", "int_to_roman(3999)", "MMMCMXCIX"), raises("rejects_zero", "int_to_roman(0)"),
               raises("rejects_4000", "int_to_roman(4000)")]},

    {"id": "calc", "entry": "calc", "prompt":
     "Write `calc(expr: str) -> float` evaluating arithmetic with + - * /, parentheses, unary + and -, "
     "integers and decimals, and arbitrary whitespace. Usual precedence, left-associative. Raise ValueError "
     "for malformed expressions and ZeroDivisionError for division by zero.",
     "tests": [approx("precedence", "calc('1 + 2 * 3')", 7), approx("parens", "calc('(1 + 2) * 3')", 9),
               approx("unary_minus_group", "calc('-(2 + 3)')", -5), approx("unary_after_op", "calc('2 * -3')", -6),
               approx("true_division", "calc('10 / 4')", 2.5), approx("left_assoc_sub", "calc('2 - 3 - 4')", -5),
               approx("left_assoc_div", "calc('8 / 4 / 2')", 1), approx("decimal", "calc('1.5 * 2')", 3),
               approx("double_unary", "calc('--1')", 1), raises("rejects_trailing_op", "calc('1 +')"),
               raises("rejects_unclosed_paren", "calc('(1')"), raises("rejects_adjacent_numbers", "calc('1 2')"),
               raises("rejects_empty", "calc('')"), raises("division_by_zero", "calc('1/0')", "ZeroDivisionError")]},

    {"id": "topo_sort", "entry": "topo_sort", "prompt":
     "Write `topo_sort(deps: dict[str, list[str]]) -> list[str]`. `deps[x]` lists nodes that must come before "
     "x. Nodes that appear only as dependencies are included too. When several nodes are available, take the "
     "lexicographically smallest first. Raise ValueError if there is a cycle.",
     "tests": [eq("chain", "topo_sort({'b':['a'],'c':['b']})", ["a", "b", "c"]),
               eq("independent_sorted", "topo_sort({'x':[],'a':[]})", ["a", "x"]),
               eq("diamond", "topo_sort({'d':['b','c'],'b':['a'],'c':['a']})", ["a", "b", "c", "d"]),
               eq("dependency_only_node", "topo_sort({'z':['y'],'b':[]})", ["b", "y", "z"]),
               eq("empty", "topo_sort({})", []), raises("rejects_cycle", "topo_sort({'a':['b'],'b':['a']})"),
               raises("rejects_self_loop", "topo_sort({'a':['a']})")]},

    {"id": "normalize_path", "entry": "normalize_path", "prompt":
     "Write `normalize_path(p: str) -> str` normalising a POSIX path: collapse repeated slashes (including a "
     "leading '//'), drop '.', resolve '..' (at the root of an absolute path it stays at root; leading '..' in "
     "a relative path is kept), drop a trailing slash except for '/'. An empty relative result is '.'.",
     "tests": [eq("parent", "normalize_path('/a/b/../c')", "/a/c"), eq("dots_and_slashes", "normalize_path('a/./b//c/')", "a/b/c"),
               eq("parent_at_root", "normalize_path('/../x')", "/x"), eq("leading_parents_kept", "normalize_path('../../a')", "../../a"),
               eq("climb_past_start", "normalize_path('a/../..')", ".."), eq("cancel_to_dot", "normalize_path('a/..')", "."),
               eq("leading_double_slash", "normalize_path('//a//b')", "/a/b"), eq("root", "normalize_path('/')", "/"),
               eq("empty", "normalize_path('')", ".")]},

    {"id": "parse_csv_line", "entry": "parse_csv_line", "prompt":
     "Write `parse_csv_line(line: str) -> list[str]` splitting one CSV line on commas. A field may be wrapped "
     "in double quotes; inside quotes commas are literal and '\"\"' is an escaped quote. Unquoted fields are "
     "taken literally (no trimming). After a closing quote only a comma or end of line may follow, otherwise "
     "raise ValueError; an unterminated quote also raises ValueError. An empty line is one empty field.",
     "tests": [eq("plain", "parse_csv_line('a,b,c')", ["a", "b", "c"]), eq("quoted_comma", "parse_csv_line('\"a,b\",c')", ["a,b", "c"]),
               eq("escaped_quotes", "parse_csv_line('\"say \"\"hi\"\"\",x')", ['say "hi"', "x"]),
               eq("empty_middle", "parse_csv_line('a,,c')", ["a", "", "c"]), eq("empty_line", "parse_csv_line('')", [""]),
               eq("trailing_comma", "parse_csv_line('a,')", ["a", ""]), eq("no_trimming", "parse_csv_line(' a , b ')", [" a ", " b "]),
               eq("empty_quoted", "parse_csv_line('\"\"')", [""]), raises("rejects_unterminated", "parse_csv_line('\"abc')"),
               raises("rejects_text_after_quote", "parse_csv_line('\"a\"b,c')")]},

    {"id": "next_business_day", "entry": "next_business_day", "prompt":
     "Write `next_business_day(date: str, holidays: list[str] = ()) -> str`. Dates are 'YYYY-MM-DD'. Return "
     "the first day strictly after `date` that is Monday-Friday and not in `holidays`. Raise ValueError for an "
     "invalid date.",
     "tests": [eq("midweek", "next_business_day('2026-10-14')", "2026-10-15"),
               eq("friday_to_monday", "next_business_day('2026-10-16')", "2026-10-19"),
               eq("saturday", "next_business_day('2026-10-17')", "2026-10-19"),
               eq("holiday_then_weekend", "next_business_day('2026-12-24', ['2026-12-25'])", "2026-12-28"),
               eq("year_boundary", "next_business_day('2026-12-31', ['2027-01-01'])", "2027-01-04"),
               raises("rejects_invalid_date", "next_business_day('2026-02-30')")]},
]

if __name__ == "__main__":
    for name, tasks in (("train", TRAIN), ("heldout", HELDOUT)):
        with open(os.path.join(HERE, f"{name}.json"), "w") as f:
            json.dump(tasks, f, indent=1)
        print(f"{name}: {len(tasks)} tasks, {sum(len(t['tests']) for t in tasks)} tests")
