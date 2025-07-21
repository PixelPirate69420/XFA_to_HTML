import re
import PyPDF2
from lxml import etree

def extract_xfa_data(pdf_path):
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            xfa_data = None

            # 1. Check for XFA data directly on the reader.
            if hasattr(reader, 'xfa') and reader.xfa:
                xfa_data = reader.xfa

            # 2. Check the AcroForm dictionary.
            elif "/AcroForm" in reader.trailer["/Root"]:
                acroform = reader.trailer["/Root"].get("/AcroForm", {})
                if "/XFA" in acroform:
                    xfa_data = acroform["/XFA"]

            # 3. Fallback: iterate through each page's resources.
            if not xfa_data:
                for page in reader.pages:
                    resources = page.get("/Resources")
                    if resources and "/XFA" in resources:
                        xfa_data = resources["/XFA"]
                        break

            if not xfa_data:
                print("No XFA data found in the PDF.")
                return None

            # Now decode the XFA data depending on its type.
            if isinstance(xfa_data, PyPDF2.generic.IndirectObject):
                xfa_data = xfa_data.get_object().get_data()
                if isinstance(xfa_data, bytes):
                    xfa_data = xfa_data.decode('utf-8', errors='replace')
            elif isinstance(xfa_data, list):
                xml_parts = []
                # Expect alternating keys and values
                for i in range(0, len(xfa_data), 2):
                    if i + 1 < len(xfa_data):
                        part = xfa_data[i+1]
                        if isinstance(part, PyPDF2.generic.IndirectObject):
                            part = part.get_object().get_data()
                        if isinstance(part, bytes):
                            part = part.decode('utf-8', errors='replace')
                        xml_parts.append(part)
                xfa_data = "\n".join(xml_parts)
            elif isinstance(xfa_data, dict):
                ordered_keys = ["preamble", "config"]
                parts = []
                for key in ordered_keys:
                    if key in xfa_data:
                        value = xfa_data[key]
                        if isinstance(value, bytes):
                            value = value.decode('utf-8', errors='replace')
                        parts.append(value)
                for key, value in xfa_data.items():
                    if key not in ordered_keys:
                        if isinstance(value, bytes):
                            value = value.decode('utf-8', errors='replace')
                        parts.append(value)
                xfa_data = "\n".join(parts)

            if not isinstance(xfa_data, str):
                xfa_data = str(xfa_data)

            return xfa_data

    except Exception as e:
        print("Error during XFA extraction:", e)
        return None

def complete_xml(xfa_str):
    # Remove leading whitespace
    xfa_str = xfa_str.lstrip()

    # Capture the first XML declaration if present
    first_decl_match = re.match(r'^(<\?xml.*?\?>)', xfa_str, re.DOTALL)
    first_decl = first_decl_match.group(1) if first_decl_match else ''

    # Remove any XML declarations found anywhere in the string
    xfa_str = re.sub(r'<\?xml.*?\?>', '', xfa_str, flags=re.DOTALL)

    # Prepend the first declaration (if any)
    if first_decl:
        xfa_str = first_decl + xfa_str

    # Try to locate a valid root element.
    if "<xdp:xdp" in xfa_str:
        start_index = xfa_str.find("<xdp:xdp")
        closing_tag = "</xdp:xdp>"
    elif "<config" in xfa_str:
        start_index = xfa_str.find("<config")
        closing_tag = "</config>"
    else:
        # If no known root found, return the original string.
        return xfa_str

    # Find the closing tag after the start_index
    end_index = xfa_str.find(closing_tag, start_index)
    if end_index == -1:
        # If closing tag not found, append it.
        xfa_str = xfa_str[start_index:] + "\n" + closing_tag
    else:
        end_index += len(closing_tag)
        xfa_str = xfa_str[start_index:end_index]
    return xfa_str

def extract_all_js(xfa_xml):
    """
    Extracts and concatenates all JavaScript code from <script> elements
    in the XFA XML (using the XFA namespace).
    """
    js_parts = []
    for script_el in xfa_xml.findall(".//{http://www.xfa.org/schema/xfa-template/3.3/}script"):
        if script_el.text:
            js_parts.append(script_el.text)
    return "\n".join(js_parts)

def save_xfa_as_html(xfa_xml, output_html_path, xslt_path=None):
    if xslt_path:
        xslt_doc = etree.parse(xslt_path)
        transform = etree.XSLT(xslt_doc)
        html_tree = transform(xfa_xml)
        html_str = etree.tostring(html_tree, pretty_print=True, method="html", encoding="utf-8").decode("utf-8")
    else:
        pretty_xml = etree.tostring(xfa_xml, pretty_print=True, encoding="unicode")
        html_str = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>XFA Content (Debug)</title>
</head>
<body>
<pre>{pretty_xml}</pre>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    print(f"Debug HTML saved as '{output_html_path}'.")

def build_ui_interpreter_stacked(xfa_xml):
    """
    Advanced UI interpreter that:
      - Ignores absolute x,y coordinates so that elements are stacked vertically.
      - Preserves all elements and cascade attributes.
      - Uses block-level elements so that elements appear one under another.
      - Interprets various XFA UI elements into HTML:
          • subform -> div with header
          • field -> label + input (or button if indicated)
          • button -> HTML button
          • text -> static text
          • textEdit -> input type='text'
          • numericEdit -> input type='number'
          • choiceList -> select with options from child "item" nodes
          • draw -> div with class "draw"
          • exclGroup -> group of radio buttons (child items)
          • checkButton -> input type='checkbox'
      - Injects all JavaScript extracted from the XFA XML.
      - Injects an advanced XFA JavaScript runtime.
      - Attaches event handlers to buttons that load the runtime and translate Acrobat JS.
    """
    ui_title = "Stacked Interpreted XFA Form"
    cascade_required = False

    def process_element(el):
        if not isinstance(el, etree._Element):
            return ""
        try:
            tag = etree.QName(el).localname.lower()
        except Exception:
            return ""
        html_parts = []
        cascade = el.get("cascade")
        if cascade:
            cascade_attr = f" data-cascade='{cascade}'"
            nonlocal cascade_required
            cascade_required = True
        else:
            cascade_attr = ""

        # Handle known UI element types:
        if tag == "subform":
            sf_name = el.get("name", "Subform")
            html_parts.append(f"<div class='subform'>")
            html_parts.append(f"<h2>{sf_name}</h2>")
            for child in el:
                html_parts.append(process_element(child))
            html_parts.append("</div>")
        elif tag == "field":
            field_name = el.get("name", "UnnamedField")
            field_label = el.get("label", field_name)
            field_value = el.get("value", "")
            field_type = el.get("type", "text")
            ui_type = el.get("uiType", "").lower()
            # Render as button if uiType indicates button OR name starts/ends with 'btn'
            if ("button" in ui_type or
                field_name.lower().startswith("btn") or
                field_name.lower().startswith("button") or
                field_name.lower().endswith("btn")):
                html_parts.append(f"<div class='field'>")
                # Optionally, you can embed Acrobat JS via a data attribute if available:
                # e.g. data-acrobat-js="app.alert('Hello from Acrobat JS');"
                html_parts.append(f"<button type='button' id='{field_name}' name='{field_name}'{cascade_attr}>"
                                  f"{field_label}</button>")
                html_parts.append("</div>")
            else:
                html_parts.append(f"<div class='field'>")
                html_parts.append(f"<label for='{field_name}'>{field_label}</label>")
                html_parts.append(f"<input type='{field_type}' id='{field_name}' name='{field_name}' value='{field_value}'{cascade_attr} />")
                html_parts.append("</div>")
        elif tag == "button":
            btn_text = el.text or "Button"
            btn_id = el.get("name", "button")
            html_parts.append(f"<div class='button'>")
            html_parts.append(f"<button type='button' id='{btn_id}' name='{btn_id}'>{btn_text}</button>")
            html_parts.append("</div>")
        elif tag == "text":
            txt = el.text or ""
            html_parts.append(f"<div class='static-text'>{txt}</div>")
        elif tag == "textedit":
            # Render textEdit as a text input
            field_name = el.get("name", "TextEdit")
            field_value = el.get("value", "")
            html_parts.append(f"<div class='textedit'>")
            html_parts.append(f"<input type='text' id='{field_name}' name='{field_name}' value='{field_value}'{cascade_attr} />")
            html_parts.append("</div>")
        elif tag == "numericedit":
            # Render numericEdit as a number input
            field_name = el.get("name", "NumericEdit")
            field_value = el.get("value", "")
            html_parts.append(f"<div class='numericedit'>")
            html_parts.append(f"<input type='number' id='{field_name}' name='{field_name}' value='{field_value}'{cascade_attr} />")
            html_parts.append("</div>")
        elif tag == "choicelist":
            # Render choiceList as a select element
            field_name = el.get("name", "ChoiceList")
            html_parts.append(f"<div class='choicelist'>")
            html_parts.append(f"<label for='{field_name}'>{field_name}</label>")
            html_parts.append(f"<select id='{field_name}' name='{field_name}'{cascade_attr}>")
            # Look for child "item" elements for options
            for item in el.findall(".//item"):
                option_value = item.get("value", item.text or "")
                option_text = item.text or option_value
                html_parts.append(f"<option value='{option_value}'>{option_text}</option>")
            html_parts.append("</select>")
            html_parts.append("</div>")
        elif tag == "draw":
            # Render draw elements as a simple div container (could later be enhanced for graphics)
            html_parts.append(f"<div class='draw' style='border:1px solid #aaa; padding:5px;'>")
            # If the draw element has text content, include it.
            if el.text and el.text.strip():
                html_parts.append(f"<span>{el.text.strip()}</span>")
            # Process child elements
            for child in el:
                html_parts.append(process_element(child))
            html_parts.append("</div>")
        elif tag == "exclgroup":
            # Render exclGroup as a set of radio buttons. Assume each child "exclChoice" represents an option.
            group_name = el.get("name", "ExclGroup")
            html_parts.append(f"<div class='exclgroup'>")
            for choice in el.findall(".//exclchoice"):
                option_value = choice.get("value", choice.text or "")
                option_label = choice.text or option_value
                html_parts.append(f"<label><input type='radio' name='{group_name}' value='{option_value}'{cascade_attr}/> {option_label}</label>")
            html_parts.append("</div>")
        elif tag == "checkbutton":
            # Render checkButton as a checkbox
            field_name = el.get("name", "CheckButton")
            html_parts.append(f"<div class='checkbutton'>")
            html_parts.append(f"<label><input type='checkbox' id='{field_name}' name='{field_name}'{cascade_attr}/> {field_name}</label>")
            html_parts.append("</div>")
        else:
            # For any other tags, process their children.
            for child in el:
                html_parts.append(process_element(child))
        return "\n".join(html_parts)

    template = xfa_xml.find(".//{http://www.xfa.org/schema/xfa-template/3.3/}template")
    if template is None:
        template = xfa_xml
    body_content = f"<div class='xfa-container'>\n{process_element(template)}\n</div>"

    # If cascade attributes are present, include the cascade JS.
    cascade_js = ""
    if cascade_required:
        cascade_js = r"""
document.addEventListener('DOMContentLoaded', function(){
    var inputs = document.querySelectorAll("input[data-cascade], button[data-cascade]");
    inputs.forEach(function(input){
        input.addEventListener('input', function(){
            var group = input.getAttribute("data-cascade");
            var cascadeInputs = document.querySelectorAll("input[data-cascade='" + group + "'], button[data-cascade='" + group + "']");
            cascadeInputs.forEach(function(cInput){
                if(cInput !== input){
                    cInput.value = input.value;
                }
            });
        });
    });
});
"""
    # Extract all JS content from the XFA.
    all_js = extract_all_js(xfa_xml)

    # Basic adapter for schCar and our new translator function.
    adapter = r"""
if (typeof schCar === 'undefined') {
    var schCar = {
        schEnt: function(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
    };
}

// Function to translate Acrobat-specific JS to web-compatible JS.
// This is a simple example. You can extend this to perform more complex translations.
function translateAcrobatJS(acrobatJS) {
    // For example, replace "app.alert" with "window.xfa.host.messageBox"
    var webJS = acrobatJS.replace(/app\.alert/g, "window.xfa.host.messageBox");
    return webJS;
}
"""

    # Advanced XFA JavaScript Runtime Support.
    xfa_runtime_js = r"""
// Advanced XFA JavaScript Runtime Support
if (typeof window.xfa === 'undefined') {
    window.xfa = {};
}
window.xfa.host = {
    messageBox: function(message, title, iconType) {
        // For advanced runtime, replace alert with a custom modal if desired.
        alert(title ? `${title}: ${message}` : message);
    },
    gotoURL: function(url) {
        window.location.href = url;
    },
    beep: function(type) {
        const audio = new Audio('https://www.soundjay.com/button/beep-07.wav');
        audio.play();
    }
};
window.xfa.form = {
    resolveNode: function(path) {
        return document.querySelector(`[name='${path}']`);
    },
    execEvent: function(eventName, node) {
        if (node && node.dispatchEvent) {
            node.dispatchEvent(new Event(eventName, { bubbles: true }));
        }
    }
};

// Define a default font object to prevent "undefined" errors.
if (typeof window.xfa.font === 'undefined') {
    window.xfa.font = {
        measureText: function(text) {
            return { width: text.length * 7 };
        }
    };
};

function executeXFAJavaScript(jsCode) {
    try {
        new Function(jsCode)();
    } catch (error) {
        console.error('Error executing XFA script:', error);
    }
}

// Advanced runtime features: asynchronous execution and event registration.
window.xfa.advanced = {
    async executeAsync(jsCode) {
        try {
            const asyncFunc = new Function('return (async () => {' + jsCode + '})')();
            await asyncFunc;
        } catch (error) {
            console.error('Error executing async XFA script:', error);
        }
    },
    registerEventHandler: function(selector, eventName, handler) {
        const elements = document.querySelectorAll(selector);
        elements.forEach(function(el) {
            el.addEventListener(eventName, handler);
        });
    }
};
"""

    # New default event binding using event delegation.
    default_bindings_js = r"""
document.addEventListener("DOMContentLoaded", function(){
    document.body.addEventListener("click", function(event){
        var target = event.target;
        if(target.tagName.toLowerCase() === "button"){
            // Check if this button has an Acrobat JS snippet attached.
            if(target.hasAttribute("data-acrobat-js")){
                // Lazy-load the XFA runtime if not already loaded.
                if(typeof window.xfaRuntimeLoaded === "undefined" || !window.xfaRuntimeLoaded){
                    console.log("Loading XFA runtime...");
                    // (In a real scenario, you might load additional runtime code here)
                    window.xfaRuntimeLoaded = true;
                }
                var acrobatJS = target.getAttribute("data-acrobat-js");
                var translatedJS = translateAcrobatJS(acrobatJS);
                try {
                    new Function(translatedJS)();
                } catch(error) {
                    console.error("Error executing translated JS:", error);
                }
            } else {
                console.log("Button clicked (default binding): " + target.id);
                window.xfa.host.messageBox("Default action for " + target.id);
            }
        }
    });
});
"""

    # Combine the adapter, advanced runtime, extracted XFA JS, and new default bindings.
    ui_js = adapter + "\n" + xfa_runtime_js + "\n" + all_js + "\n" + default_bindings_js
    full_js = cascade_js + "\n" + ui_js

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>{ui_title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      margin: 0;
      padding: 20px;
      font-family: Arial, sans-serif;
      background: #eee;
    }}
    .xfa-container {{
      display: flex;
      flex-direction: column;
      gap: 20px;
      background: #fff;
      padding: 20px;
      box-shadow: 0 0 10px rgba(0,0,0,0.1);
    }}
    .subform, .field, .button, .static-text, .textedit, .numericedit, .choicelist, .draw, .exclgroup, .checkbutton {{
      display: block;
      width: 100%;
      position: relative;
      margin-bottom: 10px;
    }}
    .subform {{
      border: 1px dashed #888;
      padding: 10px;
    }}
    .field, .button, .static-text, .textedit, .numericedit, .choicelist, .draw, .exclgroup, .checkbutton {{
      background: #fff;
      border: 1px solid #ccc;
      padding: 10px;
    }}
    label {{
      display: block;
      margin-bottom: 5px;
      font-weight: bold;
    }}
    input[type="text"], input[type="number"] {{
      padding: 5px;
      width: 100%;
      box-sizing: border-box;
    }}
    button {{
      padding: 10px 15px;
      cursor: pointer;
      font-size: 14px;
    }}
    select {{
      padding: 5px;
      width: 100%;
      box-sizing: border-box;
    }}
    .static-text {{
      background: #f9f9f9;
      border: 1px solid #ddd;
    }}
  </style>
</head>
<body>
{body_content}
<script>
{full_js}
</script>
</body>
</html>
"""
    return html_doc

if __name__ == "__main__":
    pdf_input = 'test.pdf'                    # Replace with your PDF file path.
    basic_html_output = 'output_debug.html'   # For debugging purposes.
    stacked_ui_output = 'stacked_UI.html'       # Final stacked UI output.

    xfa_content = extract_xfa_data(pdf_input)
    if xfa_content:
        completed_xml_str = complete_xml(xfa_content)
        try:
            xfa_xml = etree.fromstring(completed_xml_str.encode('utf-8'))
        except Exception as e:
            print("Error parsing XFA XML:", e)
            snippet = completed_xml_str[:200]
            print("Extracted data snippet:", snippet)
        else:
            save_xfa_as_html(xfa_xml, basic_html_output)
            ui_html = build_ui_interpreter_stacked(xfa_xml)
            with open(stacked_ui_output, "w", encoding="utf-8") as f:
                f.write(ui_html)
            print(f"Stacked UI HTML saved as '{stacked_ui_output}'.")
    else:
        print("No XFA content extracted; nothing to output.")
