# LLD: calculator

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.3
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Safe math expression evaluator. Deterministic, no LLM call needed. Accepts a math expression string, parses and evaluates it using a restricted AST walker, and returns the stringified result. Designed to be registered in `tool_registry` and invoked by agents as an MCP tool.

## Public API

### Models

| Class | Fields | Notes |
|-------|--------|-------|
| `CalcRequest` | `expression: str` | Raw math expression string (e.g., `"2 + 3 * 4"`, `"sqrt(16) + pi"`, `"2 ** 10"`). Whitespace-tolerant. Must not be empty. |
| `CalcResult` | `result: str`, `expression: str` | `result` is the stringified evaluation output (e.g., `"14"`, `"7.141592653589793"`). `expression` echoes back the original input for correlation. Result is always a string to avoid float/int ambiguity at the protocol boundary. |

### Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `evaluate` | `(request: CalcRequest) -> CalcResult` | Synchronous. Parses and evaluates the expression. Returns `CalcResult` on success. Raises `ToolExecutionError` on invalid or unsafe expressions. This is the sole public entry point. |
| `register_calculator` | `(registry: ToolRegistry) -> None` | Registers the calculator tool with `tool_registry`. Called once at startup. Wires `evaluate` as the handler with the appropriate name, description, and input schema. |

## Internal Design

### Key Design Decisions

1. **AST-based safe evaluation, not `eval()`** -- Python's `eval()` and `exec()` are arbitrary code execution vectors. The calculator uses `ast.parse()` in `"eval"` mode to produce an AST, then walks the tree with a restricted node visitor that only permits safe operations. This eliminates code injection risk entirely.

2. **Restricted node whitelist** -- The AST walker permits only these node types:
   - `ast.Expression` (top-level wrapper)
   - `ast.Constant` (numeric literals: `int`, `float`, `complex`)
   - `ast.UnaryOp` with operators `ast.UAdd`, `ast.USub` (unary `+` and `-`)
   - `ast.BinOp` with operators `ast.Add`, `ast.Sub`, `ast.Mult`, `ast.Div`, `ast.FloorDiv`, `ast.Mod`, `ast.Pow`
   - `ast.Call` for whitelisted math functions only (see below)
   - `ast.Name` for whitelisted constants only (see below)

   Any node type not in the whitelist raises `ToolExecutionError`. This means no attribute access, no subscripts, no imports, no lambdas, no comprehensions, no assignments, no string operations.

3. **Whitelisted math functions and constants** -- A static dict maps safe names to their implementations:
   - **Functions:** `abs`, `round`, `min`, `max`, `sum`, `pow`, `sqrt`, `log`, `log2`, `log10`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `ceil`, `floor`, `factorial`, `gcd`, `degrees`, `radians`, `exp`, `hypot`
   - **Constants:** `pi`, `e`, `tau`, `inf`, `nan`

   Functions are sourced from Python's `math` module and builtins. The whitelist is defined as a module-level constant dict (`_SAFE_NAMES`), not dynamically constructed.

4. **Power operator guard** -- `ast.Pow` is permitted but guarded: the exponent is evaluated first and rejected if `abs(exponent) > 10000`. This prevents denial-of-service via expressions like `2 ** 2 ** 2 ** 99` or `10 ** 1000000`. The threshold (10000) is a module-level constant (`_MAX_EXPONENT`).

5. **Expression length limit** -- Input expressions longer than 1000 characters are rejected before parsing. This is a module-level constant (`_MAX_EXPRESSION_LENGTH`). Prevents abuse via pathologically long expressions.

6. **Result is always `str`** -- `CalcResult.result` is a string. Integer results are formatted without decimal point (`"42"`, not `"42.0"`). Float results use Python's default `str()` representation. Special float values (`inf`, `-inf`, `nan`) are stringified as-is. This avoids JSON serialization ambiguity and keeps the protocol boundary clean.

7. **No LLM, no external deps** -- The calculator is pure Python stdlib (`ast`, `math`, `operator`). No AI framework, no external package. This is intentional: deterministic tools should not depend on non-deterministic components.

8. **Replaces legacy SmolAgents calculator** -- The existing codebase uses a SmolAgents `CodeAgent` as a calculator (`SynaptiCore/Tools/smolBots.py:calculater`), which runs arbitrary Python code for math. The rewrite replaces this with a safe, deterministic evaluator that requires no LLM and no code execution sandbox.

### Evaluation Pipeline

```
CalcRequest.expression
    │
    ├─ Validate: non-empty, length ≤ _MAX_EXPRESSION_LENGTH
    │
    ├─ ast.parse(expression, mode="eval")
    │   └─ SyntaxError → ToolExecutionError("Invalid expression syntax")
    │
    ├─ _SafeEvaluator.visit(ast_tree)
    │   ├─ Walk each node
    │   ├─ Reject disallowed node types → ToolExecutionError("Unsupported operation")
    │   ├─ Reject disallowed function names → ToolExecutionError("Function not allowed")
    │   ├─ Reject disallowed name references → ToolExecutionError("Name not allowed")
    │   ├─ Guard Pow exponent → ToolExecutionError("Exponent too large")
    │   └─ Evaluate permitted nodes recursively
    │
    ├─ Catch arithmetic errors (ZeroDivisionError, OverflowError, ValueError)
    │   └─ → ToolExecutionError with descriptive message
    │
    └─ Format result as str → CalcResult(result=str(value), expression=original)
```

### Module structure

```
synapticore/tools/calculator.py
    _MAX_EXPRESSION_LENGTH = 1000
    _MAX_EXPONENT = 10000
    _SAFE_NAMES: dict[str, Any]        # whitelisted functions + constants
    _SAFE_OPERATORS: dict[type, Callable]  # ast operator → implementation

    CalcRequest (Pydantic BaseModel)
    CalcResult (Pydantic BaseModel)

    class _SafeEvaluator(ast.NodeVisitor):
        visit_Expression(node) -> Any
        visit_Constant(node) -> int | float | complex
        visit_UnaryOp(node) -> Any
        visit_BinOp(node) -> Any
        visit_Call(node) -> Any
        visit_Name(node) -> Any
        generic_visit(node) -> NoReturn   # rejects all unlisted nodes

    evaluate(request: CalcRequest) -> CalcResult
    register_calculator(registry: ToolRegistry) -> None
```

### Class: `_SafeEvaluator`

Private AST node visitor. Single-use: instantiate per evaluation. Stateless aside from the tree walk.

| Method | Input | Output | Behavior |
|--------|-------|--------|----------|
| `visit_Expression` | `ast.Expression` | result of visiting `.body` | Top-level entry, delegates to body node. |
| `visit_Constant` | `ast.Constant` | `int \| float \| complex` | Returns `node.value`. Rejects non-numeric constants (strings, bytes, booleans). |
| `visit_UnaryOp` | `ast.UnaryOp` | numeric | Applies `+` or `-` to the visited operand. Rejects other unary ops (`~`, `not`). |
| `visit_BinOp` | `ast.BinOp` | numeric | Looks up `type(node.op)` in `_SAFE_OPERATORS`. For `ast.Pow`, evaluates right operand first and checks `abs(right) <= _MAX_EXPONENT`. Applies operator to visited left and right. |
| `visit_Call` | `ast.Call` | numeric | Resolves `node.func` (must be `ast.Name` with `id` in `_SAFE_NAMES` and callable). Evaluates arguments via visit. Rejects `**kwargs` and `*args` syntax. Calls the resolved function with evaluated positional args. |
| `visit_Name` | `ast.Name` | numeric | Looks up `node.id` in `_SAFE_NAMES`. Returns the mapped value (e.g., `math.pi`). Rejects unknown names. |
| `generic_visit` | any node | `NoReturn` | Raises `ToolExecutionError` with the disallowed node type name. Catchall for anything not explicitly permitted. |

## Dependencies

### Internal
- `types/common_types` -- `ToolExecutionError` (raised on evaluation failures)
- `tools/tool_registry` -- `ToolRegistry` type (used by `register_calculator` for tool registration at startup)

### External
- `ast` (stdlib -- AST parsing and node types)
- `math` (stdlib -- math functions and constants)
- `operator` (stdlib -- operator implementations for `_SAFE_OPERATORS`)
- `pydantic` (BaseModel, Field -- for `CalcRequest`, `CalcResult`)

No external AI/ML dependencies. Pure stdlib + Pydantic.

## Error Contracts

### Raised by this module

All errors raised are `ToolExecutionError` with `tool_name="calculator"`:

| Condition | `original_error` message | Trigger |
|-----------|-------------------------|---------|
| Empty expression | `"Expression is empty"` | `CalcRequest.expression` is empty or whitespace-only |
| Expression too long | `"Expression exceeds maximum length of {_MAX_EXPRESSION_LENGTH}"` | `len(expression) > _MAX_EXPRESSION_LENGTH` |
| Syntax error | `"Invalid expression syntax: {parse_error}"` | `ast.parse()` raises `SyntaxError` |
| Disallowed node | `"Unsupported operation: {node_type}"` | `generic_visit` hit -- node type not in whitelist |
| Disallowed function | `"Function not allowed: {func_name}"` | `visit_Call` -- function name not in `_SAFE_NAMES` or not callable |
| Disallowed name | `"Name not allowed: {name}"` | `visit_Name` -- name not in `_SAFE_NAMES` |
| Exponent too large | `"Exponent too large: abs({exponent}) > {_MAX_EXPONENT}"` | `visit_BinOp` with `ast.Pow` where exponent exceeds guard |
| Division by zero | `"Division by zero"` | `ZeroDivisionError` during evaluation |
| Overflow | `"Result overflow"` | `OverflowError` during evaluation |
| Math domain error | `"Math domain error: {detail}"` | `ValueError` from math functions (e.g., `sqrt(-1)`, `log(0)`) |
| Non-numeric constant | `"Non-numeric constant not allowed"` | `visit_Constant` receives a string, bytes, or boolean literal |

### Raised implicitly
- `pydantic.ValidationError` on invalid `CalcRequest` construction (e.g., missing `expression` field).

### Protocol mapping
- `ToolExecutionError` is mapped to protocol-specific errors by the protocol layers (see `common-types.md` Error-to-Protocol Mapping Guide).

## Test Plan

### Unit tests (`tests/unit/tools/test_calculator.py`)

**Basic arithmetic:**
- `"2 + 3"` -> `"5"`
- `"10 - 4"` -> `"6"`
- `"3 * 7"` -> `"21"`
- `"15 / 4"` -> `"3.75"`
- `"15 // 4"` -> `"3"`
- `"17 % 5"` -> `"2"`
- `"2 ** 8"` -> `"256"`

**Operator precedence:**
- `"2 + 3 * 4"` -> `"14"`
- `"(2 + 3) * 4"` -> `"20"` (Note: parentheses are handled by the AST parser, not the evaluator)

**Unary operators:**
- `"-5"` -> `"-5"`
- `"+3"` -> `"3"`
- `"-(2 + 3)"` -> `"-5"`

**Floating point:**
- `"1 / 3"` -> result starts with `"0.333"`
- `"0.1 + 0.2"` -> result is valid float string (not exact `"0.3"` due to IEEE 754)

**Integer formatting:**
- `"4 + 6"` -> `"10"` (not `"10.0"`)
- `"10 / 2"` -> `"5.0"` (Python float division)
- `"10 // 2"` -> `"5"` (floor division returns int)

**Math functions:**
- `"sqrt(16)"` -> `"4.0"`
- `"abs(-7)"` -> `"7"`
- `"round(3.7)"` -> `"4"`
- `"max(1, 2, 3)"` -> `"3"`
- `"min(1, 2, 3)"` -> `"1"`
- `"log(1)"` -> `"0.0"`
- `"log10(100)"` -> `"2.0"`
- `"sin(0)"` -> `"0.0"`
- `"cos(0)"` -> `"1.0"`
- `"ceil(3.2)"` -> `"4"`
- `"floor(3.8)"` -> `"3"`
- `"factorial(5)"` -> `"120"`
- `"gcd(12, 8)"` -> `"4"`

**Math constants:**
- `"pi"` -> result starts with `"3.14159"`
- `"e"` -> result starts with `"2.71828"`
- `"tau"` -> result starts with `"6.28318"`

**Combined expressions:**
- `"sqrt(16) + pi"` -> valid float string (~`"7.14159"`)
- `"2 * sin(pi / 6)"` -> valid float string (~`"1.0"`)
- `"log2(1024)"` -> `"10.0"`

**Expression echo-back:**
- For any successful evaluation, `CalcResult.expression` equals the original input string

**Security -- disallowed operations:**
- `"__import__('os')"` -> `ToolExecutionError` (disallowed function/name)
- `"open('/etc/passwd')"` -> `ToolExecutionError` (disallowed function)
- `"[x for x in range(10)]"` -> `ToolExecutionError` (list comprehension not allowed)
- `"lambda x: x + 1"` -> `ToolExecutionError` (lambda not allowed)
- `"a = 5"` -> `SyntaxError` via `ast.parse` mode="eval" (not an expression)
- `"os.system('ls')"` -> `ToolExecutionError` (attribute access not allowed)
- `"print('hello')"` -> `ToolExecutionError` (disallowed function)
- `"'hello' + 'world'"` -> `ToolExecutionError` (non-numeric constant)
- `"True + 1"` -> `ToolExecutionError` (boolean constant not allowed)

**Guard -- exponent limit:**
- `"2 ** 10000"` -> succeeds (at boundary)
- `"2 ** 10001"` -> `ToolExecutionError` (exponent too large)
- `"2 ** -10001"` -> `ToolExecutionError` (abs(exponent) too large)

**Guard -- expression length:**
- Expression of exactly 1000 characters -> succeeds (if valid)
- Expression of 1001 characters -> `ToolExecutionError` (expression too long)

**Error cases:**
- `""` (empty string) -> `ToolExecutionError` (expression is empty)
- `"   "` (whitespace only) -> `ToolExecutionError` (expression is empty)
- `"2 + "` -> `ToolExecutionError` (syntax error)
- `"1 / 0"` -> `ToolExecutionError` (division by zero)
- `"sqrt(-1)"` -> `ToolExecutionError` (math domain error)
- `"log(0)"` -> `ToolExecutionError` (math domain error)
- `"10 ** 1000000"` -> `ToolExecutionError` (exponent too large)
- `"foo(5)"` -> `ToolExecutionError` (function not allowed)
- `"x + 1"` -> `ToolExecutionError` (name not allowed)

**Serialization round-trip:**
- `CalcRequest`: `model_dump()` -> `model_validate()` preserves expression
- `CalcResult`: `model_dump()` -> `model_validate()` preserves result and expression

**Registration:**
- `register_calculator` registers tool with name `"calculator"`
- Registered tool has description, input schema matching `CalcRequest`, and working handler

## ADR References

- None pending. Calculator is pure stdlib with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
