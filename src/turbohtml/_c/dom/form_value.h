/* The submitted value of a form control, per WHATWG "constructing the entry list": an input's value attribute after
   its type's value sanitization algorithm, and a textarea's API value. Implemented in dom/form_value.c. */

#ifndef TURBOHTML_DOM_FORM_VALUE_H
#define TURBOHTML_DOM_FORM_VALUE_H

#include "dom/nodes.h"

/* The sanitized value of a text-like input (not a checkbox, radio, button, or file input) as a new str; type and value
   are the input's type and value attributes, NULL when it has none. NULL only on allocation failure. */
PyObject *th_form_input_value(th_node *input, const th_node_attr *type, const th_node_attr *value);

/* A textarea's API value as a new str: its text content with every CRLF and lone CR normalized to LF. NULL only on
   allocation failure. */
PyObject *th_form_textarea_value(th_tree *tree, th_node *textarea);

#endif /* TURBOHTML_DOM_FORM_VALUE_H */
