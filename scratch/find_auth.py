import os

def find_file(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)
    return None

auth_path = find_file("auth_state.json", os.getcwd())
print(f"Found auth_state.json at: {auth_path}")
