"""Peephole folding: exact rewrites plus a behavior differential under Node.

The folds run on the full-minify path (``minify_js``). They rewrite value-position
boolean and undefined literals into their shorter equivalents as real AST nodes, so
the printer re-parenthesises by precedence; property names, object keys and shadowed
bindings are left alone. ``test_folding_preserves_behavior`` executes each snippet and
its minified form under Node and asserts identical output.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404

import pytest

from turbohtml import JSMinify, minify_js

_NODE = shutil.which("node")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("x=true", "x=!0", id="true"),
        pytest.param("x=false", "x=!1", id="false"),
        pytest.param("x=a?true:false", "x=a?!0:!1", id="ternary"),
        pytest.param("x=true.toString()", "x=(!0).toString()", id="bool-member-parenthesized"),
        pytest.param("x={true:1,get false(){}}", "x={true:1,get false(){}}", id="bool-keys-kept"),
        pytest.param("x=a.true", "x=a.true", id="bool-property-kept"),
        pytest.param("x=undefined", "x=void 0", id="undefined"),
        pytest.param("x=undefined.y", "x=(void 0).y", id="undefined-member-parenthesized"),
        pytest.param("x=a.undefined", "x=a.undefined", id="undefined-property-kept"),
        pytest.param("var undefined=5;x=undefined", "var undefined=5;x=undefined", id="undefined-shadowed-kept"),
        # dead-code elimination drops a constant-condition branch, but only when the dropped
        # branch hoists nothing (a var or function declaration), checked across every control-flow
        # shape; an impure condition is left untouched
        pytest.param("null?1:2", "2", id="dce-null-falsy"),
        pytest.param("x?1:2", "x?1:2", id="dce-impure-cond-kept"),
        pytest.param("void 0?1:2", "2", id="dce-void-pure-falsy"),
        pytest.param("void x?1:2", "void x?1:2", id="dce-void-impure-kept"),
        pytest.param("if(0){class C{}}b", "b", id="dce-class-no-hoist-dropped"),
        # `undefined` folds to `void 0` only when nothing declares the name; a class named
        # `undefined` blocks it, while any other class lets the fold through
        pytest.param("class undefined{}x=undefined", "class undefined{}x=undefined", id="class-shadows-undefined"),
        pytest.param("class C extends D{}x=undefined", "class C extends D{}x=void 0", id="class-not-undefined-folds"),
        # conditional algebra (13.14): a repeated name test collapses to a logical, identical branches to
        # the branch, and two same-target assignments merge; an impure test or a non-ident target is kept
        pytest.param("x=a?a:b", "x=a||b", id="cond-self-or"),
        pytest.param("x=a?b:a", "x=a&&b", id="cond-self-and"),
        pytest.param("x=a?b:b", "x=b", id="cond-same-branches"),
        pytest.param("x=cond?(t=1):(t=2)", "x=t=cond?1:2", id="cond-assign-merge"),
        pytest.param("x=g()?c:c", "x=g()?c:c", id="cond-impure-test-kept"),
        pytest.param("x=a?t+=1:t+=2", "x=a?t+=1:t+=2", id="cond-compound-assign-kept"),
        pytest.param("x=a?t=1:t+=2", "x=a?t=1:t+=2", id="cond-mixed-assign-kept"),
        pytest.param("x=a?o.p=1:o.p=2", "x=a?o.p=1:o.p=2", id="cond-member-target-kept"),
        pytest.param("x=a?t=1:u=2", "x=a?t=1:u=2", id="cond-diff-target-kept"),
        # same-op short-circuit chains left-rotate to drop the parens (13.13: same operands, order,
        # and result either way); a mixed-op pair keeps its grouping
        pytest.param("x=a&&(b&&c)", "x=a&&b&&c", id="and-chain-rotates"),
        pytest.param("x=a||(b||c)", "x=a||b||c", id="or-chain-rotates"),
        pytest.param("x=a??(b??c)", "x=a??b??c", id="nullish-chain-rotates"),
        pytest.param("x=a&&(b&&(c&&d))", "x=a&&b&&c&&d", id="and-chain-rotates-deep"),
        pytest.param("x=a&&((b&&c)&&d)", "x=a&&b&&c&&d", id="and-chain-rotates-left-nested"),
        pytest.param("x=a&&(b||c)", "x=a&&(b||c)", id="mixed-op-kept"),
        pytest.param("x=a??(b&&c)", "x=a??(b&&c)", id="nullish-and-mix-kept"),
        pytest.param("if(a)b&&c", "a&&b&&c", id="if-chain-rotates"),
        pytest.param("x=a?a:b||c", "x=a||b||c", id="cond-self-or-chain-rotates"),
        # same-type operands make loose equality strict (7.2.14 step 1), so === weakens to ==; an
        # operand of unknown static type (a name, member, or literal against a name) keeps ===
        pytest.param('x=typeof a==="string"', 'x=typeof a=="string"', id="eq-typeof-string-weakens"),
        pytest.param('x=typeof a!=="undefined"', 'x=typeof a!="undefined"', id="ne-typeof-string-weakens"),
        pytest.param("x=typeof a===typeof b", "x=typeof a==typeof b", id="eq-typeof-typeof-weakens"),
        pytest.param("x=!a===!b", "x=!a==!b", id="eq-bang-bang-weakens"),
        pytest.param("x=void a===void b", "x=void a==void b", id="eq-void-void-weakens"),
        pytest.param('x=a==="s"', 'x=a==="s"', id="eq-unknown-string-kept"),
        pytest.param("x=a===1", "x=a===1", id="eq-unknown-number-kept"),
        pytest.param("x=a===null", "x=a===null", id="eq-null-kept"),
        pytest.param("x=a===void 0", "x=a===void 0", id="eq-undefined-kept"),
        pytest.param("x=1===a", "x=1===a", id="eq-number-unknown-kept"),
        # -a coerces to an unknown numeric-or-bigint and delete yields its own boolean, but neither
        # is a shape static_type vouches for, so both keep ===
        pytest.param("x=-a===-b", "x=-a===-b", id="eq-minus-unary-kept"),
        pytest.param("x=delete a.b===c", "x=delete a.b===c", id="eq-delete-kept"),
        # a consequent that always jumps makes the else keyword redundant (14.6.2: the alternate
        # runs exactly when the test was falsy either way), so the alternate joins the chain; a
        # falling-through consequent and Annex-B `else function` keep their else
        pytest.param("function f(){if(a)throw e;else g()}", "function f(){if(a)throw e;g()}", id="abrupt-else-spliced"),
        pytest.param("while(x){if(a)break;else g()}", "while(x){if(a)break;g()}", id="abrupt-break-else-spliced"),
        pytest.param(
            "function f(){if(a)return 1;else if(b)return 2;else g();h()}",
            "function f(){if(a)return 1;if(b)return 2;g(),h()}",
            id="abrupt-else-chain-spliced",
        ),
        pytest.param(
            "function f(){if(a){g();return 1}else h()}",
            "function f(){if(a)return g(),1;h()}",
            id="abrupt-block-else-spliced",
        ),
        pytest.param(
            "function f(){if(a)return;else function q(){}q()}",
            "function f(){if(a)return;else function q(){}q()}",
            id="annex-b-else-function-kept",
        ),
        pytest.param("if(a)g();else{var x=1;h(x)}", "if(a)g();else{var x=1;h(x)}", id="multi-stmt-else-block-kept"),
        # a tail return of undefined is redundant (10.2.1.4: falling off the end returns undefined);
        # a valued or non-tail return, and `delete` (valued, not void), stay
        pytest.param("function f(){g();return}", "function f(){g()}", id="tail-bare-return-dropped"),
        pytest.param("function f(){return}", "function f(){}", id="tail-only-return-dropped"),
        pytest.param("function f(){return void g()}", "function f(){g()}", id="tail-return-void-unwrapped"),
        pytest.param("function f(){h();return void g()}", "function f(){h(),g()}", id="tail-return-void-seq"),
        pytest.param("function f(){return undefined}", "function f(){}", id="tail-return-undefined-dropped"),
        pytest.param("function f(){h();return void 0}", "function f(){h()}", id="tail-return-pure-seq-unwraps"),
        pytest.param("function f(){a();b();return void 0}", "function f(){a(),b()}", id="tail-return-pure-seq-keeps"),
        pytest.param("var f=()=>{return void g()}", "var f=()=>{g()}", id="tail-return-void-arrow"),
        pytest.param(
            "function f(){while(a)b();return void 0}",
            "function f(){while(a)b()}",
            id="tail-return-pure-after-loop-dropped",
        ),
        pytest.param("function f(){return g()}", "function f(){return g()}", id="tail-valued-return-kept"),
        pytest.param(
            "function f(){return delete o.p}", "function f(){return delete o.p}", id="tail-return-delete-kept"
        ),
        pytest.param(
            "function f(){return void g(),h()}", "function f(){return void g(),h()}", id="tail-seq-valued-kept"
        ),
        pytest.param(
            "function f(){for(;;){return void g()}}",
            "function f(){for(;;)return void g()}",
            id="loop-nested-return-void-kept",
        ),
    ],
)
def test_folds(source: str, expected: str) -> None:
    assert minify_js(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # fold alone (mangle off) keeps unreachable code after a return when it hoists a var: the hoist
        # check descends every control-flow shape and short-circuits across both branch slots. The full
        # pipeline goes further and drops the binding (see test_compresses); here fold must not.
        pytest.param("function f(){return;if(a)var x}", id="unreach-if-then"),
        pytest.param("function f(){return;if(a){}else var y}", id="unreach-if-else"),
        pytest.param("function f(){return;for(var i=0;;){}}", id="unreach-for-init"),
        pytest.param("function f(){return;for(;;)var x}", id="unreach-for-body"),
        pytest.param("function f(){return;for(var k in o){}}", id="unreach-forin-bind"),
        pytest.param("function f(){return;for(k in o)var x}", id="unreach-forin-body"),
    ],
)
def test_fold_keeps_unreachable_that_hoists(source: str) -> None:
    assert minify_js(source, JSMinify(mangle=False)) == source


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # adjacent same-kind declarations merge; a different kind or a gap does not
        pytest.param("var a=1;var b=2", "var a=1,b=2", id="var-merge"),
        pytest.param("let a=1;const b=2", "let a=1;const b=2", id="decl-kind-mismatch-kept"),
        pytest.param("var a=1;f();var b=2", "var a=1;f();var b=2", id="decl-not-adjacent"),
        # if -> logical / conditional (14.6, 13.13, 13.14); a !x test drops the negation
        pytest.param("if(a)b()", "a&&b()", id="if-and"),
        pytest.param("if(!a)b()", "a||b()", id="if-not-or"),
        pytest.param("if(a){b()}", "a&&b()", id="if-block-flatten"),
        pytest.param("if(a)b();else c()", "a?b():c()", id="if-else-cond"),
        pytest.param("if(!a)b();else c()", "a?c():b()", id="if-not-else-flip"),
        pytest.param("if(a){b()}else{c()}", "a?b():c()", id="if-else-blocks-flatten"),
        pytest.param("if(a){b();c()}", "a&&(b(),c())", id="if-multi-stmt-block-merges"),
        pytest.param("if(a){var b;c()}", "if(a){var b;c()}", id="if-multi-stmt-block-kept"),
        pytest.param("if(a){}else b()", "a||b()", id="if-empty-then-to-or"),
        pytest.param("if(a);else b()", "a||b()", id="if-empty-stmt-then-to-or"),
        pytest.param("if(a)b();else{}", "a&&b()", id="if-empty-else-dropped"),
        pytest.param("if(a)b();else{;}", "a&&b()", id="if-empty-stmt-else-dropped"),
        pytest.param("if(!a){}else b()", "a&&b()", id="if-empty-then-neg-to-and"),
        pytest.param("if(a){}else{}", "if(a){}", id="if-both-empty-guard-kept"),
        # an empty then with a non-expression else is left intact (nothing shorter to fold to)
        pytest.param("if(a){}else{var x=1}", "if(a){}else var x=1", id="if-empty-then-nonexpr-else-kept"),
        pytest.param("if(a){}else{for(;;);var z}", "if(a){}else{for(;;);var z}", id="if-empty-then-multi-else-kept"),
        pytest.param("function f(){if(a){return 1}return 2}", "function f(){return a?1:2}", id="guard-block-return"),
        # guard clause -> conditional return; cascades right
        pytest.param("function f(){if(a)return 1;return 2}", "function f(){return a?1:2}", id="guard-return"),
        pytest.param(
            "function f(){if(a)return 1;if(b)return 2;return 3}",
            "function f(){return a?1:b?2:3}",
            id="guard-cascade",
        ),
        # sequence merge (13.16); a directive prologue is never swept in; nested sequences flatten
        pytest.param("a();b();c()", "a(),b(),c()", id="seq-merge"),
        pytest.param("a,b;c,d;e", "a,b,c,d,e", id="seq-flatten"),
        pytest.param('function f(){"use strict";a();b()}', 'function f(){"use strict";a(),b()}', id="directive-kept"),
        pytest.param("function f(){a();b();return c}", "function f(){return a(),b(),c}", id="seq-into-return"),
        # double negation in a conditional test peels fully
        pytest.param("x=!!a?1:0", "x=a?1:0", id="double-negation"),
        # a["x"] -> a.x and {"x":1} -> {x:1} for a bare-identifier key; otherwise the quotes stay
        pytest.param("x=a['x']", "x=a.x", id="member-to-dot"),
        pytest.param("x=a['aB_$9']", "x=a.aB_$9", id="member-to-dot-charset"),
        pytest.param("x=a?.['x']", "x=a?.x", id="optional-member-to-dot"),
        pytest.param("x=a['1x']", "x=a['1x']", id="member-digit-start-kept"),
        pytest.param("x=a['a-b']", "x=a['a-b']", id="member-non-ident-kept"),
        pytest.param("x={'k':1}", "x={k:1}", id="key-unquote"),
        pytest.param("x={'__proto__':1}", "x={'__proto__':1}", id="key-proto-kept"),
        pytest.param("x={'abcdefghi':1}", "x={abcdefghi:1}", id="key-nine-char-non-proto"),
        pytest.param("x={'a-b':1}", "x={'a-b':1}", id="key-non-ident-kept"),
        # exact integer arithmetic and string concatenation fold (13.15); the cases that could
        # round, go negative, coerce or lose an escape are left untouched
        pytest.param("x=1+2", "x=3", id="int-add"),
        pytest.param("x=2+3*4", "x=14", id="int-precedence-cascade"),
        pytest.param("x=7-3", "x=4", id="int-sub"),
        pytest.param("x=3-5", "x=3-5", id="int-sub-negative-kept"),
        pytest.param("x=1.5+2", "x=1.5+2", id="float-add-kept"),
        pytest.param("x=1000+0", "x=1e3", id="int-add-then-canon"),
        pytest.param('x="a"+"b"', 'x="ab"', id="string-concat"),
        pytest.param("x='a'+'b'", "x='a'+'b'", id="string-concat-single-quote-kept"),
        pytest.param('x=1+"a"', 'x=1+"a"', id="mixed-add-kept"),
        pytest.param("x=1e3+2", "x=1e3+2", id="exponent-operand-kept"),
        pytest.param("x=9999999999999999+1", "x=9999999999999999+1", id="oversize-int-kept"),
        pytest.param("x=0*7", "x=0", id="int-mul-zero"),
        pytest.param("x=99999999*99999999", "x=99999999*99999999", id="int-mul-overflow-kept"),
        pytest.param('x="a"+5', 'x="a"+5', id="string-plus-number-kept"),
        pytest.param("x=\"a\"+'b'", "x=\"a\"+'b'", id="concat-mixed-quote-kept"),
        # more folded literals than the program's initial owned-buffer capacity, forcing it to grow
        pytest.param(
            "x=[" + ",".join(f"{index}+1" for index in range(18)) + "]",
            "x=[" + ",".join(str(index + 1) for index in range(18)) + "]",
            id="many-folded-literals",
        ),
        # a single-use local const with a literal initializer inlines and the declaration drops; a
        # const read twice, with a non-literal init, or at the (observable) top level is kept
        pytest.param("function f(){const x=1;return x}", "function f(){return 1}", id="const-inline"),
        pytest.param(
            "function f(){const x='a';return x.length}", "function f(){return'a'.length}", id="const-inline-string"
        ),
        pytest.param(
            "function f(){const x=/r/;return x.test(s)}", "function f(){return/r/.test(s)}", id="const-inline-regex"
        ),
        pytest.param("function f(){const x=true;return x}", "function f(){return!0}", id="const-inline-bool"),
        pytest.param("function f(){const x=1;return ()=>x}", "function f(){return()=>1}", id="const-inline-closure"),
        pytest.param("function f(){const x=42;return x*2}", "function f(){return 84}", id="const-inline-then-fold"),
        pytest.param("function f(){for(const x=5;c;)h(x)}", "function f(){for(;c;)h(5)}", id="const-inline-for-init"),
        pytest.param("function f(){const x=1;return x+x}", "function f(){const a=1;return a+a}", id="const-twice-kept"),
        # a non-literal single use collapses only when its declaration immediately precedes the use as a
        # whole `return`/`throw` value (nothing runs between, no closure captures it); otherwise it stays
        pytest.param("function f(){const x=g();return x}", "function f(){return g()}", id="nonliteral-return-collapse"),
        pytest.param("function f(){var x=a.b;throw x}", "function f(){throw a.b}", id="nonliteral-throw-collapse"),
        pytest.param("function f(){const x=g();h(x)}", "function f(){const a=g();h(a)}", id="nonliteral-nonjump-kept"),
        # a binding that is written (reassigned, updated, or a destructuring / for-in assignment target) is
        # never inlined: the read/write split keeps the value off an illegal `[5]=arr` / `for(5 in o)` slot
        pytest.param(
            "function f(){let x=5;[x]=arr;return x}",
            "function f(){let a=5;return[a]=arr,a}",
            id="no-inline-destructure-write",
        ),
        pytest.param(
            "function f(){let x=5;for(x in o);}", "function f(){let a=5;for(a in o);}", id="no-inline-forin-write"
        ),
        pytest.param("function f(){var x=1;x=2;g(x)}", "function f(){var a=1;a=2,g(a)}", id="no-inline-reassigned"),
        # `x=EXPR` folded into the very next read of x -- the temporary the fold pass leaves as `(x=EXPR,x)`
        pytest.param("function f(){var r;r=g();return r}", "function f(){return g()}", id="collapse-assign-return"),
        pytest.param("function f(){var r=0;r=g();throw r}", "function f(){throw g()}", id="collapse-assign-throw"),
        pytest.param("function f(){var x=1;x=2;return x}", "function f(){return 2}", id="collapse-reassign-literal"),
        pytest.param(
            "function f(){var r;r=g();return r+1}", "function f(){var a;return a=g(),a+1}", id="collapse-not-sole-read"
        ),
        pytest.param(
            "function f(){var x;x=g(),y;return x}",
            "function f(){var a;return a=g(),y,a}",
            id="collapse-other-elem-between",
        ),
        pytest.param("function f(){a=1,b=2}", "function f(){a=1,b=2}", id="collapse-free-assign-kept"),
        pytest.param("function f(){var x;x=1;return x=2,x}", "function f(){return 2}", id="collapse-twice-written"),
        # `(t=V, t)` where t is read elsewhere drops just the redundant trailing read, keeping the assign
        pytest.param(
            "function f(a){return a=a||{},a}", "function f(a){return a=a||{}}", id="collapse-assign-value-read"
        ),
        pytest.param(
            "function f(){var x=1;x++;return x}", "function f(){var a=1;return a++,a}", id="no-inline-updated"
        ),
        pytest.param(
            "function f(){var x=1;x+=2;return x}", "function f(){var a=1;return a+=2,a}", id="no-inline-compound"
        ),
        pytest.param("function f(o){o.x+=1}", "function f(a){a.x+=1}", id="compound-assign-member"),
        pytest.param("function f(){g+=1}", "function f(){g+=1}", id="compound-assign-free"),
        pytest.param(
            "function f(){const a=1,b=2;return a+b}",
            "function f(){const b=1,a=2;return b+a}",
            id="const-multi-declarator-kept",
        ),
        pytest.param(
            "function f(){const[x]=a;return x}", "function f(){const [b]=a;return b}", id="const-destructuring-kept"
        ),
        pytest.param("const x=1;f(x)", "const x=1;f(x)", id="const-global-kept"),
        # a non-`!` unary test keeps its operator; `!!` peels both negations (make_logical/make_cond)
        pytest.param("if(~a)b()", "~a&&b()", id="if-and-unary-non-not"),
        pytest.param("if(!!a)b()", "a&&b()", id="if-and-double-negation"),
        pytest.param("if(~a)b();else c()", "~a?b():c()", id="if-cond-unary-non-not"),
        # a dead branch whose alternate or loop body (not just its head) hoists is still kept;
        # one whose nested if / loop hoists nowhere is dropped (the body is scanned either way)
        pytest.param("if(0){if(q)g();else var v}f()", "if(0)if(q)g();else var v;f()", id="dead-if-alt-hoist-kept"),
        pytest.param("if(0){for(;c;)var v}f()", "if(0)for(;c;)var v;f()", id="dead-for-body-hoist-kept"),
        pytest.param("if(0){for(k in o)var v}f()", "if(0)for(k in o)var v;f()", id="dead-forin-body-hoist-kept"),
        pytest.param("if(0){if(q)while(c)g()}f()", "f()", id="dead-if-no-hoist-dropped"),
        pytest.param("if(0){for(;c;)g()}f()", "f()", id="dead-for-no-hoist-dropped"),
        pytest.param("if(0){for(k in o)g()}f()", "f()", id="dead-forin-no-hoist-dropped"),
        pytest.param("if(0){for(k of o)g()}f()", "f()", id="dead-forof-no-hoist-dropped"),
        # an object/member key with an ASCII code point above `z` is not an identifier, so quotes stay
        pytest.param("x=a['a{b']", "x=a['a{b']", id="member-above-z-kept"),
        # an unread local binding is dead code: a side-effect-free var/let/const and an unused function
        # declaration drop (ECMA-262 has no observable effect for an unread binding); a side-effecting
        # initializer, a used binding, a for-in/of loop binding and a top-level (observable) name stay
        pytest.param("function f(){var x=1;return 2}", "function f(){return 2}", id="drop-unused-var"),
        pytest.param("function f(){let x=function(){};return 2}", "function f(){return 2}", id="drop-unused-fn-expr"),
        pytest.param("function f(){const x=1;g()}", "function f(){g()}", id="drop-unused-const"),
        pytest.param("function f(){function h(){}return 2}", "function f(){return 2}", id="drop-unused-function"),
        # one dead declarator drops out of a multi-declarator statement; the statement empties only when
        # its last declarator goes, and a destructuring sibling is skipped over
        pytest.param(
            "function f(){var a=g(),x=1,b=2;return a+b}",
            "function f(){var b=g(),a=2;return b+a}",
            id="drop-middle-declarator",
        ),
        pytest.param("function f(){var x=1,y=g();return y}", "function f(){return g()}", id="drop-first-declarator"),
        pytest.param(
            "function f(){var {a}=o,x=1;return a}", "function f(){var {a:a}=o;return a}", id="drop-past-destructure"
        ),
        pytest.param("function f(){var x=g();return 2}", "function f(){var a=g();return 2}", id="keep-sideeffect-init"),
        # the side-effect-free check accepts every literal kind, a function/arrow and a unary over a pure operand
        pytest.param("function f(){var x='s';return 1}", "function f(){return 1}", id="drop-unused-string"),
        pytest.param("function f(){var x=/r/;return 1}", "function f(){return 1}", id="drop-unused-regex"),
        pytest.param("function f(){var x=1n;return 1}", "function f(){return 1}", id="drop-unused-bigint"),
        pytest.param("function f(){var x=()=>1;return 2}", "function f(){return 2}", id="drop-unused-arrow"),
        pytest.param("function f(){var x=!0;return 1}", "function f(){return 1}", id="drop-unused-unary"),
        pytest.param("function f(){for(var[a]in o)g()}", "function f(){for(var [a] in o)g()}", id="keep-forin-pattern"),
        pytest.param(
            "function f(){function h(){}return h()+h()}",
            "function f(){function a(){}return a()+a()}",
            id="keep-twice-used-fn",
        ),
        # a function used once becomes an expression at the use; a use in a loop or a nested function
        # runs repeatedly and would build a fresh closure each time, so it is kept
        pytest.param(
            "function f(){function h(){return 1}return h}",
            "function f(){return function(){return 1}}",
            id="inline-single-use-fn",
        ),
        pytest.param(
            "function f(){function h(){}for(var i=0;i<3;i++)a.push(h)}",
            "function f(){function c(){}for(var b=0;b<3;b++)a.push(c)}",
            id="keep-fn-used-in-loop",
        ),
        pytest.param(
            "function f(){function h(){}g(function(){return h})}",
            "function f(){function a(){}g(function(){return a})}",
            id="keep-fn-used-in-closure",
        ),
        pytest.param("function f(){for(var k in o)g(k)}", "function f(){for(var a in o)g(a)}", id="keep-forin-binding"),
        pytest.param("function f(){return;for(;;){var x}}", "function f(){}", id="drop-unreachable-hoisted"),
        pytest.param("var g=1", "var g=1", id="keep-global-var"),
        pytest.param("with(o){var x=1;f()}", "with(o){var x=1;f()}", id="keep-under-with"),
        # a void guard-return at a function body's top level inverts to `cond||(rest)` when the rest is
        # all expressions; a valued/trailing return, a declaration in the rest, or a nested block is kept
        pytest.param("function f(a){if(a)return;g();h()}", "function f(a){a||(g(),h())}", id="guard-return-invert"),
        pytest.param("function f(a){if(a)return;g()}", "function f(a){a||g()}", id="guard-return-single"),
        pytest.param(
            "function f(a){g();if(a)return}", "function f(a){g();if(a)return}", id="guard-return-trailing-kept"
        ),
        pytest.param(
            "function f(a){if(a)return 1;g();h()}",
            "function f(a){if(a)return 1;g(),h()}",
            id="guard-return-valued-kept",
        ),
        pytest.param(
            "function f(a){if(a)return;g();var x=h();x()}",
            "function f(b){if(b)return;g();var a=h();a()}",
            id="guard-return-decl-kept",
        ),
        pytest.param(
            "function g(a){while(1){if(a)return;h()}}",
            "function g(a){while(1){if(a)return;h()}}",
            id="guard-return-in-loop-kept",
        ),
        # a dead store whose value is impure keeps the value as an expression statement; a pure sequence
        # head is dropped; a twice-used function in a block keeps its name; a multi-declarator single use
        # is not inlined (the whole statement cannot be emptied without losing its siblings)
        pytest.param("function f(){var x;x=g()}", "function f(){g()}", id="dead-store-impure"),
        pytest.param("function f(){0,g()}", "function f(){g()}", id="seq-drop-pure-head"),
        pytest.param("function f(x){return x,g()}", "function f(a){return g()}", id="seq-drop-pure-local-head"),
        pytest.param("function f(y){return g(),y,h()}", "function f(a){return g(),h()}", id="seq-drop-pure-mid"),
        pytest.param(
            "function f(){var r;return h(),r=g(),r}", "function f(){return h(),g()}", id="seq-collapse-after-effect"
        ),
        pytest.param("function f(){var r;return r=1,r}", "function f(){return 1}", id="seq-collapse-literal"),
        # a single-use literal rides to the tail of the adjacent return/throw's comma sequence (the
        # earlier operands cannot change a never-written literal); an impure initializer would reorder
        # against them and stays, as does a read that is not the sequence's value
        pytest.param("function f(){var x=1;g();return x}", "function f(){return g(),1}", id="literal-seq-tail-inline"),
        pytest.param("function f(){var x=1;g();throw x}", "function f(){throw g(),1}", id="literal-seq-tail-throw"),
        pytest.param(
            "function f(){var x=h();g();return x}",
            "function f(){var a=h();return g(),a}",
            id="impure-seq-tail-kept",
        ),
        pytest.param(
            "function f(){var x=1;g();return x+1}",
            "function f(){var a=1;return g(),a+1}",
            id="literal-non-tail-kept",
        ),
        # the adjacent jump carries no value the read could be: a bare return (the closure read
        # may run before the declaration) and a non-sequence return value both keep the binding
        pytest.param(
            "function f(){if(c){q(()=>x);var x=1;return}g()}",
            "function f(){if(c){q(()=>a);var a=1;return}g()}",
            id="literal-bare-return-kept",
        ),
        pytest.param(
            "function f(){q(()=>x);var x=1;return 2}",
            "function f(){q(()=>a);var a=1;return 2}",
            id="literal-other-return-value-kept",
        ),
        pytest.param(
            "function f(){var x;x=g(),foo();return x}",
            "function f(){var a;return a=g(),foo(),a}",
            id="seq-collapse-gap-kept",
        ),
        pytest.param(
            "function f(){var x;return x=g(),x+x}",
            "function f(){var a;return a=g(),a+a}",
            id="seq-collapse-twice-read-kept",
        ),
        pytest.param(
            "function f(x){if(x){function h(){}h();h()}}",
            "function f(a){if(a){function h(){}h(),h()}}",
            id="block-function-kept",
        ),
        pytest.param(
            "function f(){var a=g(),x=1;return x}",
            "function f(){var b=g(),a=1;return a}",
            id="multi-declarator-single-use",
        ),
    ],
)
def test_compresses(source: str, expected: str) -> None:
    assert minify_js(source) == expected


def _run(code: str) -> str:
    assert _NODE is not None  # the callers are skipped when node is unavailable
    result = subprocess.run([_NODE, "-e", code], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    return result.stdout + result.stderr


@pytest.mark.skipif(_NODE is None, reason="node not available")
@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("console.log(true,false,!true,typeof undefined,void 0===undefined)", id="literals"),
        pytest.param("console.log([true,false,undefined].map(x=>x===void 0))", id="array"),
        pytest.param("var o={true:1,undefined:2};console.log(o.true,o.undefined)", id="keys-not-folded"),
        pytest.param("(function(undefined){console.log(undefined)})(7)", id="shadowed-undefined"),
        pytest.param("console.log(true.toString(),undefined?.x,undefined??'d')", id="member-and-operators"),
        # constant-condition dead-code elimination: short circuits, ternaries and ifs
        pytest.param("console.log(1&&'a',0&&'b',1||'c',0||'d')", id="dce-and-or"),
        pytest.param("console.log(null??'e',0??'f',1?'g':'h',0?'i':'j')", id="dce-nullish-ternary"),
        pytest.param("console.log(''&&1,'s'&&2,/r/&&3,(void 0)??4,undefined&&5)", id="dce-truthiness-kinds"),
        pytest.param("console.log(true&&false||'x',1&&2&&3)", id="dce-chained"),
        pytest.param("if(1)console.log('taken');else console.log('not')", id="dce-if-true"),
        pytest.param("if(0)console.log('not');else console.log('taken')", id="dce-if-false-else"),
        pytest.param("if(0)console.log('gone');console.log('after')", id="dce-if-false-no-else"),
        pytest.param(
            "(function(){function f(){return 7;console.log('dead')}console.log(f())})()", id="dce-unreachable-tail"
        ),
        # a dead branch that hoists a var or function must be kept, not dropped: node_hoists
        # has to descend each control-flow form to find the hoisted binding
        pytest.param("(function(){if(0){for(var i=0;i<1;i++)var a=1}console.log(typeof a)})()", id="hoist-for"),
        pytest.param("(function(){if(0){for(var k in {x:1})var b=1}console.log(typeof b)})()", id="hoist-forin"),
        pytest.param("(function(){if(0){for(var v of [1])var c=1}console.log(typeof c)})()", id="hoist-forof"),
        pytest.param("(function(){if(0){while(0)var d=1}console.log(typeof d)})()", id="hoist-while"),
        pytest.param("(function(){if(0){do var e=1;while(0)}console.log(typeof e)})()", id="hoist-dowhile"),
        pytest.param("(function(){if(0){lbl:{var g=1}}console.log(typeof g)})()", id="hoist-label"),
        pytest.param(
            "(function(){if(0){try{var h=1}catch(o){var j=1}finally{var k=1}}"
            "console.log(typeof h,typeof j,typeof k)})()",
            id="hoist-try",
        ),
        pytest.param(
            "(function(){if(0){switch(1){case 1:var p=1;default:var q=1}}console.log(typeof p,typeof q)})()",
            id="hoist-switch",
        ),
        pytest.param("(function(){if(0){with({}){var r=1}}console.log(typeof r)})()", id="hoist-with"),
        pytest.param("(function(){if(0){s();function s(){}}console.log(typeof s)})()", id="hoist-function"),
        pytest.param("(function(){if(0)var t=1;console.log(typeof t)})()", id="hoist-bare-var"),
        pytest.param(
            "(function(){if(0){if(1)var u=1;else var w=1}console.log(typeof u,typeof w)})()", id="hoist-nested-if"
        ),
        pytest.param(
            "(function(){if(0){switch(2){case 1:console.log('x')}}console.log('ok')})()", id="dead-switch-no-hoist"
        ),
        pytest.param("(function(){if(1)function af(){return 9}console.log(typeof af)})()", id="if-true-function-kept"),
        # non-`!`/`void` unary operands are not pure constants, so the short circuit stays
        pytest.param("console.log(-1&&'a',~0&&'b',typeof x&&'c')", id="dce-non-pure-unary"),
        # `undefined` must not fold to `void 0` when some binding shadows it; the shadow
        # scan has to recognize it in array, object, function, class and catch positions
        pytest.param("(function(){var [undefined]=[5];console.log(undefined)})()", id="undefined-array-bind"),
        pytest.param(
            "(function(){var {undefined}={undefined:6};console.log(undefined)})()", id="undefined-object-bind"
        ),
        pytest.param(
            "(function(){function undefined(){return 7}console.log(undefined())})()", id="undefined-function-bind"
        ),
        pytest.param("(function(){class undefined{}console.log(typeof undefined)})()", id="undefined-class-bind"),
        pytest.param("(function(){try{throw 8}catch(undefined){console.log(undefined)}})()", id="undefined-catch-bind"),
        # number truthiness across every literal form the zero-test inspects
        pytest.param("console.log(0xF&&1,0XF&&1,0o7&&1,0O7&&1,0b1&&1,0B1&&1)", id="radix-truthiness"),
        pytest.param("console.log(1e1&&1,1E1&&1,2n&&1,1.5&&1,1_0&&1,0.0&&1)", id="exponent-bigint-fraction"),
        pytest.param("console.log((void 0)&&1,(void 0)??2,void 0?1:2)", id="void-operand"),
        pytest.param("console.log((typeof x)??1,(!0)??2,null??3)", id="nullish-non-void-operands"),
        # dead branches that hoist on only one side of a control-flow node, so node_hoists
        # has to evaluate the second operand of its || rather than short-circuit
        pytest.param("(function(){if(0){if(x)g();else var y}console.log(typeof y)})()", id="hoist-if-else-only"),
        pytest.param("(function(){if(0){for(;;)var z}console.log(typeof z)})()", id="hoist-for-body-only"),
        pytest.param("(function(){if(0){for(k in {})var z}console.log(typeof z)})()", id="hoist-forin-body-only"),
        pytest.param("(function(){if(0){try{g()}catch(o){var x}}console.log(typeof x)})()", id="hoist-catch-only"),
        pytest.param(
            "(function(){if(0){try{g()}catch(o){h()}finally{var x}}console.log(typeof x)})()", id="hoist-finally-only"
        ),
        pytest.param("(function(){if(0){try{g()}catch(o){h()}}console.log('ok')})()", id="dead-try-no-hoist"),
        # `undefined` bound through an initializer, a class body and a try block, so the
        # shadow scan evaluates the later operands of its || chains
        pytest.param(
            "(function(){var q=function undefined(){};console.log(typeof q,undefined)})()", id="undefined-init-bind"
        ),
        pytest.param(
            "(function(){class X{m(){var undefined=1;return undefined}}console.log(new X().m())})()",
            id="undefined-class-body-bind",
        ),
        pytest.param(
            "(function(){class Y extends(class{m(){var undefined=1;return undefined}}){};console.log(new Y().m())})()",
            id="undefined-superclass-bind",
        ),
        pytest.param(
            "(function(){try{var undefined=5}catch(o){}console.log(undefined)})()", id="undefined-try-block-bind"
        ),
        pytest.param(
            "(function(){try{g()}catch(o){var undefined=1}console.log(undefined)})()", id="undefined-catch-block-bind"
        ),
        pytest.param(
            "(function(){try{}finally{var undefined=2}console.log(undefined)})()", id="undefined-finally-bind"
        ),
        pytest.param("(function(){if(1){var undefined=3}console.log(undefined)})()", id="undefined-block-bind"),
        pytest.param("(function(){if(0)g();else var undefined=4;console.log(undefined)})()", id="undefined-else-bind"),
        pytest.param(
            "(function(){for(var i=0;i<1;i++){var undefined=5}console.log(undefined)})()", id="undefined-for-body-bind"
        ),
        # unreachable-tail cut: a terminator that is the last statement, and a tail that hoists
        pytest.param("(function(){function f(){console.log('x');return 1}console.log(f())})()", id="terminator-last"),
        pytest.param("(function(){function f(){return 1;var x}console.log(f())})()", id="tail-hoists-kept"),
    ],
)
def test_folding_preserves_behavior(snippet: str) -> None:
    assert _run(snippet) == _run(minify_js(snippet))
