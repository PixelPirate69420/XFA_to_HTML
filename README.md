# XFA_to_HTML
Extract, transform, and render interactive PDF forms in your browser — without Acrobat.

This script provides a full pipeline to extract XFA (XML Forms Architecture) content from PDF files and convert it into HTML with working UI elements and JavaScript logic. It's especially useful for developers migrating legacy Acrobat workflows to modern web applications, or anyone needing to debug or visualize XFA-based PDFs.

📄 Input: PDF files with embedded XFA data
🌐 Output: Debug HTML + Fully-interpreted UI with optional JavaScript runtime
🔧 Use case: Replace Acrobat dependencies, inspect dynamic forms, or repurpose form UIs for the web

🔧 Features
✅ Extracts raw XFA XML data from AcroForms or embedded PDF metadata

✅ Cleans and reconstructs partial or malformed XML blocks

✅ Converts XFA form elements into web-friendly HTML

✅ Simulates Acrobat JavaScript with a built-in runtime

✅ Supports buttons, inputs, choice lists, subforms, scripts, and more

✅ Optional support for advanced cascade behavior and script execution

🧰 Requirements
Install the required Python dependencies:


pip install PyPDF2 lxml
🚀 Usage

python PDF-XML_to_HTML.py
This will:

Load a PDF file (test.pdf by default)

Extract and parse any embedded XFA data

Generate:

output_debug.html: Raw XFA XML previewed in HTML

stacked_UI.html: Rendered HTML form using a stacked layout

Optional: Customize filenames
You can modify the script to change the input/output paths:

python
Copy
Edit
pdf_input = 'your_input.pdf'
basic_html_output = 'raw_xfa_debug.html'
stacked_ui_output = 'rendered_form.html'
🧠 How it works
extract_xfa_data: Scans multiple potential XFA storage locations inside the PDF and extracts the embedded XML.

complete_xml: Cleans up malformed XFA by reassembling root tags and removing duplicate XML declarations.

build_ui_interpreter_stacked: Converts the form structure into clean HTML with embedded JavaScript for basic runtime behavior.

JavaScript Runtime: A simulated XFA environment is injected to handle basic Acrobat JS like app.alert(), xfa.host.messageBox(), etc.

📁 Example Output
output_debug.html – XFA as pretty-printed XML inside an HTML <pre> tag

stacked_UI.html – Interactive HTML form emulating the original PDF layout

Includes buttons, inputs, choice lists, JavaScript events, and cascade behavior

🛠️ Known Limitations
Currently optimized for "stacked" UI rendering — coordinates and layout fidelity are not preserved.

Only basic JavaScript commands are translated from Acrobat to browser-safe code.

Some XFA-specific logic (like event ordering or full XFA data bindings) may be limited.

