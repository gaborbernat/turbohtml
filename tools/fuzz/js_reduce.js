// Fork of UglifyJS 111746bbae5f55c88e3b82b42f14fd0f3129ea53; see LICENSE-UGLIFYJS.
// Use the parent's finding predicate because reduction must not execute JavaScript.
const UGLIFY = require("../bench/node/node_modules/uglify-js");

const LIST = UGLIFY.List;

module.exports = function reduce_test(testcase, reproduces, budget) {
  const REPLACEMENTS = [ "1", "0" ];
  const steps = 4;
  const step = 1 / steps;
  let changed = false;
  var transformer = new UGLIFY.TreeTransformer(function(node, descend, in_list) {
    if (changed) return;
    if (node instanceof UGLIFY.AST_Accessor) return;
    if (node instanceof UGLIFY.AST_Directive) return;
    if (!in_list && node instanceof UGLIFY.AST_EmptyStatement) return;
    if (node instanceof UGLIFY.AST_Label) return;
    if (node instanceof UGLIFY.AST_LabelRef) return;
    if (node instanceof UGLIFY.AST_Toplevel) return;
    var parent = transformer.parent();
    if (node instanceof UGLIFY.AST_SymbolFunarg && parent instanceof UGLIFY.AST_Accessor) return;
    if (!in_list && parent.rest !== node && node instanceof UGLIFY.AST_SymbolDeclaration) return;
    if (typeof node.start._permute === "undefined") node.start._permute = 0;
    if (node.start._permute >= REPLACEMENTS.length) return;
    if (parent instanceof UGLIFY.AST_Assign && parent.left === node) return;
    if (parent instanceof UGLIFY.AST_DefaultValue && parent.name === node) return;
    if (parent instanceof UGLIFY.AST_DestructuredKeyVal && parent.value === node) return;
    if (parent instanceof UGLIFY.AST_Unary && parent.expression === node) switch (parent.operator) {
     case "++":
     case "--":
     case "delete":
      return;
    }
    if (parent instanceof UGLIFY.AST_VarDef && parent.name === node) return;
    if (parent instanceof UGLIFY.AST_ClassMethod && parent.value === node) return;
    if (parent instanceof UGLIFY.AST_ExportDeclaration) return;
    if (parent instanceof UGLIFY.AST_ExportDefault) return;
    if (parent instanceof UGLIFY.AST_ExportForeign) return;
    if (parent instanceof UGLIFY.AST_ExportReferences) return;
    if (node instanceof UGLIFY.AST_VarDef && parent.definitions.length == 1
        && transformer.parent(1) instanceof UGLIFY.AST_ExportDeclaration) {
      return;
    }
    if (parent instanceof UGLIFY.AST_For && parent.init === node && node instanceof UGLIFY.AST_Definitions) return node;
    if (parent instanceof UGLIFY.AST_ForEnumeration && parent.init === node) return node;
    if (node.TYPE == "Call" && node.expression instanceof UGLIFY.AST_Super) return;
    if (node instanceof UGLIFY.AST_Super && parent.TYPE == "Call" && parent.expression === node) return node;
    if (node instanceof UGLIFY.AST_Array) {
      var expr = node.elements[0];
      if (expr && !(expr instanceof UGLIFY.AST_Hole)) {
        node.start._permute++;
        changed = true;
        return expr instanceof UGLIFY.AST_Spread ? expr.expression : expr;
      }
    } else if (node instanceof UGLIFY.AST_Await) {
      node.start._permute++;
      changed = true;
      return node.expression;
    } else if (node instanceof UGLIFY.AST_Binary) {
      var permute = ((node.start._permute += step) * steps | 0) % 4;
      var expr = [ node.left, node.right ][permute & 1];
      if (expr instanceof UGLIFY.AST_Destructured) expr = expr.transform(
          new UGLIFY.TreeTransformer(function(node, descend) {
        if (node instanceof UGLIFY.AST_DefaultValue) return new UGLIFY.AST_Assign({
          operator: "=",
          left: node.name.transform(this),
          right: node.value,
          start: {}
        });
        if (node instanceof UGLIFY.AST_DestructuredKeyVal) return new UGLIFY.AST_ObjectKeyVal(node);
        if (node instanceof UGLIFY.AST_Destructured) {
          node = new (node instanceof UGLIFY.AST_DestructuredArray ? UGLIFY.AST_Array : UGLIFY.AST_Object)(node);
          descend(node, this);
        }
        return node;
      }));
      changed = true;
      return permute < 2 ? expr : wrap_with_console_log(expr);
    } else if (node instanceof UGLIFY.AST_BlockStatement) {
      if (in_list && node.body.filter(function(node) {
        return node instanceof UGLIFY.AST_Const || node instanceof UGLIFY.AST_Let;
      }).length == 0) {
        node.start._permute++;
        changed = true;
        return LIST.splice(node.body);
      }
    } else if (node instanceof UGLIFY.AST_Call) {
      var expr = [
        !(node.expression instanceof UGLIFY.AST_Super) && node.expression, node.args[0], null
      ][((node.start._permute += step) * steps | 0) % 3];
      if (expr) {
        changed = true;
        return expr instanceof UGLIFY.AST_Spread ? expr.expression : expr;
      }
      if (node.expression instanceof UGLIFY.AST_Arrow && node.expression.value) {
        var seq = node.args.slice();
        seq.push(node.expression.value);
        changed = true;
        return to_sequence(seq);
      }
      if (node.expression instanceof UGLIFY.AST_Function) {
        var scope = transformer.find_parent(UGLIFY.AST_Scope), seq = [];
        node.expression.body.forEach(function(node) {
          var expr = node instanceof UGLIFY.AST_Exit ? node.value : node.body;
          if (expr instanceof UGLIFY.AST_Node && !UGLIFY.is_statement(expr) && can_hoist(expr, scope)) {
            seq.push(expr);
          }
        });
        changed = true;
        return to_sequence(seq);
      }
    } else if (node instanceof UGLIFY.AST_Catch) {
      node.start._permute++;
      changed = true;
      return null;
    } else if (node instanceof UGLIFY.AST_Conditional) {
      changed = true;
      return [ node.condition, node.consequent, node.alternative ][((node.start._permute += step) * steps | 0) % 3];
    } else if (node instanceof UGLIFY.AST_DefaultValue) {
      node.start._permute++;
      changed = true;
      return node.name;
    } else if (node instanceof UGLIFY.AST_Defun) {
      switch (((node.start._permute += step) * steps | 0) % 2) {
       case 0:
        changed = true;
        return LIST.skip;

       default:
        if (can_hoist(node, transformer.find_parent(UGLIFY.AST_Scope))) {
          var body = node.body;
          node.body = [];
          body.push(node);
          changed = true;
          return LIST.splice(body);
        }
      }
    } else if (node instanceof UGLIFY.AST_DestructuredArray) {
      var expr = node.elements[0];
      if (expr && !(expr instanceof UGLIFY.AST_Hole)) {
        node.start._permute++;
        changed = true;
        return expr;
      }
    } else if (node instanceof UGLIFY.AST_DestructuredObject) {
      var expr = node.properties[0];
      if (expr) {
        node.start._permute++;
        changed = true;
        return expr.value;
      }
    } else if (node instanceof UGLIFY.AST_DWLoop) {
      var expr = [ node.condition, node.body, null ][(node.start._permute * steps | 0) % 3];
      node.start._permute += step;
      if (!expr) {
        if (node.body[0] instanceof UGLIFY.AST_Break) {
          if (node instanceof UGLIFY.AST_Do) {
            changed = true;
            return LIST.skip;
          }
          expr = node.condition;
        }
      }
      if (expr && (expr !== node.body || !has_loopcontrol(expr, node, parent))) {
        changed = true;
        return to_statement(expr);
      }
    } else if (node instanceof UGLIFY.AST_ExportDeclaration) {
      node.start._permute++;
      changed = true;
      return node.body;
    } else if (node instanceof UGLIFY.AST_ExportDefault) {
      node.start._permute++;
      changed = true;
      return to_statement(node.body);
    } else if (node instanceof UGLIFY.AST_Finally) {
      node.start._permute++;
      changed = true;
      return null;
    } else if (node instanceof UGLIFY.AST_For) {
      var expr = [ node.init, node.condition, node.step, node.body ][(node.start._permute * steps | 0) % 4];
      node.start._permute += step;
      if (expr && (expr !== node.body || !has_loopcontrol(expr, node, parent))) {
        changed = true;
        return to_statement_init(expr);
      }
    } else if (node instanceof UGLIFY.AST_ForEnumeration) {
      var expr;
      switch ((node.start._permute * steps | 0) % 4) {
       case 0:
        expr = node.object;
        break;

       case 1:
        expr = wrap_with_console_log(node.object);
        break;

       case 2:
        if (has_loopcontrol(node.body, node, parent)) break;
        expr = node.body;
        break;

       case 3:
        if (!(node.init instanceof UGLIFY.AST_Var)) break;
        if (node.init.definitions[0].name instanceof UGLIFY.AST_Destructured) break;
        expr = node.init;
        break;
      }
      node.start._permute += step;
      if (expr) {
        changed = true;
        return to_statement_init(expr);
      }
    } else if (node instanceof UGLIFY.AST_If) {
      var expr = [ node.condition, node.body, node.alternative, node ][(node.start._permute * steps | 0) % 4];
      node.start._permute += step;
      if (expr === node) {
        if (node.alternative) {
          expr = node.clone();
          expr.alternative = null;
          changed = true;
          return expr;
        }
      } else if (expr) {
        changed = true;
        return to_statement(expr);
      }
    } else if (node instanceof UGLIFY.AST_LabeledStatement) {
      if (node.body instanceof UGLIFY.AST_Statement && !has_loopcontrol(node.body, node.body, node)) {
        node.start._permute = REPLACEMENTS.length;
        changed = true;
        return node.body;
      }
    } else if (node instanceof UGLIFY.AST_Object) {
      var expr = node.properties[0];
      if (expr instanceof UGLIFY.AST_ObjectKeyVal) {
        expr = expr.value;
      } else if (expr instanceof UGLIFY.AST_Spread) {
        expr = expr.expression;
      } else if (expr && expr.key instanceof UGLIFY.AST_Node) {
        expr = expr.key;
      } else {
        expr = null;
      }
      if (expr) {
        node.start._permute++;
        changed = true;
        return expr;
      }
    } else if (node instanceof UGLIFY.AST_PropAccess) {
      var expr = [
        !(node.expression instanceof UGLIFY.AST_Super) && node.expression,
        node.property instanceof UGLIFY.AST_Node && !(parent instanceof UGLIFY.AST_Destructured) && node.property
      ][node.start._permute++ % 2];
      if (expr) {
        changed = true;
        return expr;
      }
    } else if (node instanceof UGLIFY.AST_SimpleStatement) {
      if (node.body instanceof UGLIFY.AST_Call && node.body.expression instanceof UGLIFY.AST_Function) {
        node.start._permute++;
        if (can_hoist(node.body.expression, transformer.find_parent(UGLIFY.AST_Scope))) {
          changed = true;
          return LIST.splice(node.body.expression.body);
        }
      }
    } else if (node instanceof UGLIFY.AST_Switch) {
      var expr = [
        node.expression, node.body[0] && node.body[0].expression, node.body[0]
      ][(node.start._permute * steps | 0) % 4];
      node.start._permute += step;
      if (expr && (!(expr instanceof UGLIFY.AST_Statement) || !has_loopcontrol(expr, node, parent))) {
        changed = true;
        return expr instanceof UGLIFY.AST_SwitchBranch ? new UGLIFY.AST_BlockStatement({
          body: expr.body.slice(),
          start: {}
        }) : to_statement(expr);
      }
    } else if (node instanceof UGLIFY.AST_Try) {
      var body = [
        node.body, node.bcatch && node.bcatch.body, node.bfinally && node.bfinally.body, null
      ][(node.start._permute * steps | 0) % 4];
      node.start._permute += step;
      if (body) {
        changed = true;
        return new UGLIFY.AST_BlockStatement({
          body: body,
          start: {}
        });
      } else {
        if (node.body[0] instanceof UGLIFY.AST_Break || node.body[0] instanceof UGLIFY.AST_Return) {
          changed = true;
          return node.body[0];
        }
      }
    } else if (node instanceof UGLIFY.AST_Unary) {
      node.start._permute++;
      changed = true;
      return node.expression;
    } else if (node instanceof UGLIFY.AST_Var) {
      if (node.definitions.length == 1 && node.definitions[0].value) {
        node.start._permute++;
        changed = true;
        return to_statement(node.definitions[0].value);
      }
    } else if (node instanceof UGLIFY.AST_VarDef) {
      if (node.value && !(node.name instanceof UGLIFY.AST_Destructured || parent instanceof UGLIFY.AST_Const)) {
        node.start._permute++;
        changed = true;
        return new UGLIFY.AST_VarDef({
          name: node.name,
          start: {}
        });
      }
    }
    if (in_list) {
      if (parent instanceof UGLIFY.AST_Switch && parent.expression != node) {
        node.start._permute++;
        changed = true;
        return LIST.skip;
      }
      if (node instanceof UGLIFY.AST_Statement) {
        node.start._permute++;
        changed = true;
        return LIST.skip;
      }
      if (!(parent instanceof UGLIFY.AST_Sequence) || parent.expressions.length > 1) {
        node.start._permute++;
        changed = true;
        return LIST.skip;
      }
    } else if (parent.rest === node) {
      node.start._permute++;
      changed = true;
      return null;
    }
    var newNode = UGLIFY.is_statement(node) ? new UGLIFY.AST_EmptyStatement({
      start: {}
    }) : UGLIFY.parse(REPLACEMENTS[node.start._permute % REPLACEMENTS.length | 0], {
      expression: true
    });
    newNode.start._permute = ++node.start._permute;
    changed = true;
    return newNode;
  }, function(node, in_list) {
    if (node instanceof UGLIFY.AST_Definitions) {
      if (node.definitions.length == 0) return in_list ? LIST.skip : new UGLIFY.AST_EmptyStatement({
        start: {}
      });
    } else if (node instanceof UGLIFY.AST_ObjectMethod) {
      if (!/Function$/.test(node.value.TYPE)) return new UGLIFY.AST_ObjectKeyVal({
        key: node.key,
        value: node.value,
        start: {}
      });
    } else if (node instanceof UGLIFY.AST_Sequence) {
      if (node.expressions.length == 1) return node.expressions[0];
    } else if (node instanceof UGLIFY.AST_Try) {
      if (!node.bcatch && !node.bfinally) return new UGLIFY.AST_BlockStatement({
        body: node.body,
        start: {}
      });
    }
  });
  let tree;
  try {
    tree = UGLIFY.parse(testcase, {
      module: true
    });
  } catch (error) {
    if (error.name === "SyntaxError") return testcase;
    throw error;
  }
  for (let pass = 0; pass < 3; pass++) {
    tree.walk(new UGLIFY.TreeWalker(function(node) {
      node.start = {
        ...node.start,
        _permute: 0
      };
    }));
    let accepted = false;
    for (let iteration = 0; iteration < budget; iteration++) {
      changed = false;
      const candidate = tree.clone(true).transform(transformer);
      if (!changed) break;
      let code;
      try {
        code = candidate.print_to_string();
        UGLIFY.parse(code, {
          module: true
        });
      } catch (error) {
        if (error.name === "SyntaxError" || error instanceof TypeError) continue;
        throw error;
      }
      if (code.length < testcase.length && reproduces(code)) {
        testcase = code;
        tree = candidate;
        accepted = true;
      }
    }
    if (!accepted) break;
  }
  return testcase;
};

function has_loopcontrol(body, loop, label) {
  var found = false;
  var walker = new UGLIFY.TreeWalker(function(node) {
    if (found) return true;
    if (node instanceof UGLIFY.AST_LoopControl && this.loopcontrol_target(node) === loop) {
      return found = true;
    }
  });
  if (label instanceof UGLIFY.AST_LabeledStatement) walker.push(label);
  walker.push(loop);
  body.walk(walker);
  return found;
}

function can_hoist(body, scope) {
  var found = false;
  var walker = new UGLIFY.TreeWalker(function(node) {
    if (found) return true;
    if (node instanceof UGLIFY.AST_Exit) return found = true;
    if (node instanceof UGLIFY.AST_NewTarget) return found = true;
    if (node instanceof UGLIFY.AST_Scope) {
      if (node === body) return;
      if (node instanceof UGLIFY.AST_Arrow || node instanceof UGLIFY.AST_AsyncArrow)
        node.argnames.forEach(function(sym) {
        sym.walk(walker);
      });
      return true;
    }
    if (node instanceof UGLIFY.AST_Super) return found = true;
    if (node instanceof UGLIFY.AST_SymbolDeclaration || node instanceof UGLIFY.AST_SymbolRef) switch (node.name) {
     case "await":
      if (/^Async/.test(scope.TYPE)) return found = true;
      return;

     case "yield":
      if (/Generator/.test(scope.TYPE)) return found = true;
      return;
    }
  });
  body.walk(walker);
  return !found;
}

function merge_sequence(array, node) {
  if (node instanceof UGLIFY.AST_Sequence) {
    array.push.apply(array, node.expressions);
  } else {
    array.push(node);
  }
  return array;
}

function to_sequence(expressions) {
  if (expressions.length == 0) return new UGLIFY.AST_Number({
    value: 0,
    start: {}
  });
  if (expressions.length == 1) return expressions[0];
  return new UGLIFY.AST_Sequence({
    expressions: expressions.reduce(merge_sequence, []),
    start: {}
  });
}

function to_statement(node) {
  return UGLIFY.is_statement(node) ? node : new UGLIFY.AST_SimpleStatement({
    body: node,
    start: {}
  });
}

function to_statement_init(node) {
  return node instanceof UGLIFY.AST_Const || node instanceof UGLIFY.AST_Let ? new UGLIFY.AST_BlockStatement({
    body: [ node ],
    start: {}
  }) : to_statement(node);
}

function wrap_with_console_log(node) {
  return new UGLIFY.AST_Call({
    expression: new UGLIFY.AST_Dot({
      expression: new UGLIFY.AST_SymbolRef({
        name: "console",
        start: {}
      }),
      property: "log",
      start: {}
    }),
    args: [ node ],
    start: {}
  });
}
