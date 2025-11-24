import base64

def load_image_base64(path):
    with open(path, "rb") as img:
        return base64.b64encode(img.read()).decode()