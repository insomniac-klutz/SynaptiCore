from importlib.metadata import version, PackageNotFoundError

base_packages = [
    "python-dotenv",
    "numpy",
    "pandas",
    "transformers",
    "torch",
    "pymupdf",
    "matplotlib"
]

lm_packages = [
    "smolagents",
    "litellm",
    "langgraph",
    "langchain_community",
    "langchain"
]

aux_packages = [
    "snowflake-connector-python",
    "boto3"
]

prvd_packages = [
    "google-generativeai",
]

requirements = []

package_groups = {
    "Base Packages": base_packages,
    "Language Model Packages": lm_packages,
    "Auxiliary Packages": aux_packages,
    "Prvd Packs":prvd_packages
}

for group_name, packages in package_groups.items():
    requirements.append(f"# {group_name}\n")
    for package in packages:
        try:
            package_version = version(package)
            requirements.append(f"{package}=={package_version}\n")
        except PackageNotFoundError:
            requirements.append(f"# {package} is not installed\n")
    requirements.append("\n")

with open("requirements.txt", "w") as file:
    file.writelines(requirements)

# smolagents==1.5.0