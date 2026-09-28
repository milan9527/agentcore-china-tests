"""Retrieve a known remote Browser file through its existing CDP connection."""
import base64


def read_remote_file(context, remote_path):
    page = context.new_page()
    try:
        page.set_content('<input id="transfer" type="file">')
        cdp = context.new_cdp_session(page)
        cdp.send("DOM.enable")
        root = cdp.send("DOM.getDocument")["root"]["nodeId"]
        node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": "#transfer"})["nodeId"]
        cdp.send("DOM.setFileInputFiles", {"nodeId": node, "files": [remote_path]})
        encoded = page.locator("#transfer").evaluate("""async input => {
          const bytes = new Uint8Array(await input.files[0].arrayBuffer());
          let binary = '';
          for (let offset=0; offset<bytes.length; offset+=8192)
            binary += String.fromCharCode(...bytes.subarray(offset, offset+8192));
          return btoa(binary);
        }""")
        return base64.b64decode(encoded)
    finally:
        page.close()
