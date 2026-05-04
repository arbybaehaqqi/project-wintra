import os

EXCLUDED_DIRS = {'.git', 'intraday_cache'}

def generate_tree(root_path, prefix=""):
    entries = []

    try:
        items = sorted(os.listdir(root_path))
    except PermissionError:
        return [prefix + "└── [Permission Denied]"]

    # filter excluded dirs
    items = [
        item for item in items
        if not (os.path.isdir(os.path.join(root_path, item)) and item in EXCLUDED_DIRS)
    ]

    for i, item in enumerate(items):
        full_path = os.path.join(root_path, item)
        is_last = (i == len(items) - 1)

        connector = "└── " if is_last else "├── "
        entries.append(prefix + connector + item)

        if os.path.isdir(full_path):
            extension = "    " if is_last else "│   "
            entries.extend(generate_tree(full_path, prefix + extension))

    return entries


def export_tree(root_path, output_file):
    root_path = os.path.abspath(root_path)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(root_path + "\n")
        tree_lines = generate_tree(root_path)
        for line in tree_lines:
            f.write(line + "\n")


if __name__ == "__main__":
    root_directory = r"C:\Users\ARBY\Documents\Microservice\project-wintra"  # change this
    output_txt = "tree_manifest.txt"

    export_tree(root_directory, output_txt)
    print(f"Tree manifest exported to {output_txt}")
