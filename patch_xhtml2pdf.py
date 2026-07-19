import os
import sys

# Find the xhtml2pdf context.py file
venv_path = sys.prefix
context_file = os.path.join(venv_path, 'Lib', 'site-packages', 'xhtml2pdf', 'context.py')

if os.path.exists(context_file):
    with open(context_file, 'r') as f:
        content = f.read()
    
    # Replace the problematic import
    new_content = content.replace(
        'from reportlab.platypus.frames import Frame, ShowBoundaryValue',
        '''from reportlab.platypus.frames import Frame
try:
    from reportlab.platypus.frames import ShowBoundaryValue
except ImportError:
    ShowBoundaryValue = None'''
    )
    
    with open(context_file, 'w') as f:
        f.write(new_content)
    
    print(f"✅ Patched {context_file}")
else:
    print(f"❌ Could not find {context_file}")