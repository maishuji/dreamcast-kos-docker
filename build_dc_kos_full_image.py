""" 
This script is used to build a docker image with ready to use for Dreamcast development.
"""

import subprocess
import argparse
import requests

# Function to filter tags that end with '24'
def filter_tags_by_year(tags, year):
    year_pattern = year[-2:]  # Extract the last two digits of the year (e.g., '24' from '13JAN24')
    filtered_tags = [tag for tag in tags if tag.endswith(year_pattern)]  # Keep only tags that end with '24'
    print(filtered_tags)
    return filtered_tags

# Function to fetch tags from the GitHub repository for KallistiOS, and include master
def fetch_snapshot_kos_tags(year):
    url = "https://api.github.com/repos/maishuji/KallistiOS/git/refs/tags"
    response = requests.get(url)
    if response.status_code == 200:
        tags = [ref['ref'].replace('refs/tags/', '') for ref in response.json()]
        return filter_tags_by_year(tags, year)
    else:
        print("Failed to fetch tags from KallistiOS.")
        return []
    
# Function to fetch tags from the GitHub repository for KallistiOS, and include master
def fetch_snapshot_kosports_tags(year):
    url = "https://api.github.com/repos/maishuji/kos-ports/git/refs/tags"
    response = requests.get(url)
    if response.status_code == 200:
        tags = [ref['ref'].replace('refs/tags/', '') for ref in response.json()]
        return filter_tags_by_year(tags, year)
    print("Failed to fetch tags from KallistiOS.")
    return []

# Function to fetch branches from the GitLab repository
def fetch_release_branches_GLdc():
    url = "https://gitlab.com/api/v4/projects/quentin.cartier.dev%2FGLdc/repository/branches"
    response = requests.get(url)
    if response.status_code == 200:
        branches = [branch['name'] for branch in response.json()]
        # Only suggest the release branches or the master branch
        filtered_branches = [branch for branch in branches if branch.startswith("release/") or branch == "master"]
        return filtered_branches
    else:
        print("Failed to fetch branches.")
        return []

# Function to prompt user for selection from a list of options
def prompt_choice(prompt, choices):
    print(prompt)
    for i, choice in enumerate(choices, 1):
        print(f"{i}. {choice}")
    
    while True:
        try:
            selection = int(input(f"Select an option (1-{len(choices)}): "))
            if 1 <= selection <= len(choices):
                return choices[selection - 1]
            print("Invalid selection. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def choose_snapshot_kos():
    years = ["2024", "2025", "master"]
    kos_year = prompt_choice("\nPlease choose the year for the snapshot for Kos (or choose master for lastest):", years)
    if(kos_year == "master"):
        snapshot_kos = kos_year
    else:
        # Fetch the avail release tags for the selected year
        snapshot_kos_choices = fetch_snapshot_kos_tags(kos_year)
        # Prompt user to select snapshot_kos
        snapshot_kos = prompt_choice("\nPlease choose a snapshot_kos:", snapshot_kos_choices)
    return snapshot_kos
    
def choose_snapshot_kosports():
    years = ["2024", "2025", "master"]
    kosPorts_year = prompt_choice("\nPlease choose the year for the snapshot for kos-ports (or choose master for lastest):", years)
    if(kosPorts_year == "master"):
        snapshot_kosports = kosPorts_year
    else:
        snapshot_kosports_choices = fetch_snapshot_kosports_tags(kosPorts_year)
        snapshot_kosports = prompt_choice("\nChoose a kos-ports snapshot :", snapshot_kosports_choices)
    return snapshot_kosports

def choose_snapshot_gldc():
    """
    Choose which release branch to use for GLdc
    """
    branches = fetch_release_branches_GLdc()
    if branches:
        snapshot_gldc = prompt_choice("\nChoose a release branch for GLdc (master for latest):", branches)
    else:
        print("No branches found. Exiting...")
        exit(1)
    return snapshot_gldc

def print_settings(args, snapshot_kos, snapshot_kosports, snapshot_gldc, docker_build_command):
    # Build the Docker image with the selected options
    print("\n----------> Print settings <----------")
    print("Building Docker image with the following options:")
    print(f"Username:           \t\t {args.username}")
    print(f"Toolchain profile   \t\t {args.profile}")
    print(f"snapshot_kos:        \t\t {snapshot_kos}")
    print(f"snapshot_kos-ports:  \t\t {snapshot_kosports}")
    print(f"snapshot_gldc branch:\t\t {snapshot_gldc}")
    print("\nRunning docker command:\n\t", " ".join(docker_build_command))
    print("--------------------------------------")

def main():
    parser = argparse.ArgumentParser(description="Build a Docker image with specified username and version tag.")
    parser.add_argument("-u", "--username", required=True, type=str, help="Docker username (neeeded for docker image creation)")
    parser.add_argument("-p", "--profile", 
        type=str, 
        required=False, 
        default="stable", 
        help="dc-chain profile : e.g 15.0.1-dev. To specify if need a specific version of toolchain (default stable)")
    
    args = parser.parse_args()
    snapshot_kos = choose_snapshot_kos()
    snapshot_kosports = choose_snapshot_kosports()
    snapshot_gldc = choose_snapshot_gldc()

    # TODO: args.profile is not used yet
    tag = f"14.2.1-dev-"
    if snapshot_kos == "master":
        tag += "latest"
    else:
        tag += f"{snapshot_kos.lower()}"

    # We only specify in the tag if using a specific tag
    if snapshot_kosports != "master":
        tag += f"-kp{snapshot_kosports.lower()}"
    if snapshot_gldc != "master":
        # Only extract the ddmmyy part (as it is a branch, 
        # it sould be initially release/ddmmyy. E.g release/10JAN24)
        tag += f"-gl{snapshot_gldc[-7:].lower()}"

    docker_build_command = [
        "docker", "build",
        "--build-arg", f"snapshot_kos={snapshot_kos}",
        "--build-arg", f"snapshot_kosports={snapshot_kosports}",
        "--build-arg", f"snapshot_gldc={snapshot_gldc}",
        "-t", f"{args.username}/dc-kos-image:{tag}", "./kos-ready/"
    ]

    print_settings(args, snapshot_kos, snapshot_kosports, snapshot_gldc,docker_build_command)

    confirm_choices = ["Yes", "No"]
    if prompt_choice("Do you want to continue ?", confirm_choices) == "Yes" :
        print("Running ...")
        # Execute the Docker build command
        subprocess.run(docker_build_command)
    else:
        print("Operation cancelled ... ")
        exit(1)

if __name__ == "__main__":
    main()
