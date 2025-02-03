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
def fetch_snapshotKos_tags(year):
    url = "https://api.github.com/repos/maishuji/KallistiOS/git/refs/tags"
    response = requests.get(url)
    if response.status_code == 200:
        tags = [ref['ref'].replace('refs/tags/', '') for ref in response.json()]
        return filter_tags_by_year(tags, year)
    else:
        print("Failed to fetch tags from KallistiOS.")
        return []
    
# Function to fetch tags from the GitHub repository for KallistiOS, and include master
def fetch_snapshotKosPorts_tags(year):
    url = "https://api.github.com/repos/maishuji/kos-ports/git/refs/tags"
    response = requests.get(url)
    if response.status_code == 200:
        tags = [ref['ref'].replace('refs/tags/', '') for ref in response.json()]
        return filter_tags_by_year(tags, year)
    else:
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
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def choose_snapshotKos():
    years = ["2024", "2025", "master"]
    kos_year = prompt_choice("\nPlease choose the year for the snapshot for Kos (or choose master for lastest):", years)
    if(kos_year == "master"):
        snapshotKos = kos_year
    else:
        # Fetch the avail release tags for the selected year
        snapshotKos_choices = fetch_snapshotKos_tags(kos_year)
        # Prompt user to select snapshotKos
        snapshotKos = prompt_choice("\nPlease choose a snapshotKos:", snapshotKos_choices)
    return snapshotKos
    
def choose_snapshotKosPorts():
    years = ["2024", "2025", "master"]
    kosPorts_year = prompt_choice("\nPlease choose the year for the snapshot for kos-ports (or choose master for lastest):", years)
    if(kosPorts_year == "master"):
        snapshotKosPorts = kosPorts_year
    else:
        snapshotKosPorts_choices = fetch_snapshotKosPorts_tags(kosPorts_year)
        snapshotKosPorts = prompt_choice("\nChoose a kos-ports snapshot :", snapshotKosPorts_choices)
    return snapshotKosPorts

def choose_snapshotGLdc():
    """
    Choose which release branch to use for GLdc
    """
    branches = fetch_release_branches_GLdc()
    if branches:
        snapshotGLdc = prompt_choice("\nChoose a release branch for GLdc (master for latest):", branches)
    else:
        print("No branches found. Exiting...")
        exit(1)
    return snapshotGLdc

def print_settings(args, snapshotKos, snapshotKosPorts, snapshotGLdc, docker_build_command):
    # Build the Docker image with the selected options
    print("\n----------> Print settings <----------")
    print(f"Building Docker image with the following options:")
    print(f"Username:           \t\t {args.username}")
    print(f"Toolchain profile   \t\t {args.profile}")
    print(f"snapshotKos:        \t\t {snapshotKos}")
    print(f"snapshotKos-ports:  \t\t {snapshotKosPorts}")
    print(f"snapshotGLdc branch:\t\t {snapshotGLdc}")
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
    
    snapshotKos = choose_snapshotKos()
    snapshotKosPorts = choose_snapshotKosPorts()
    snapshotGLdc = choose_snapshotGLdc()
    
    # TODO: args.profile is not used yet
    tag = f"14.2.1-dev-"
    if snapshotKos == "master":
        tag += "latest"
    else:
        tag += f"{snapshotKos.lower()}"

    # We only specify in the tag if using a specific tag
    if snapshotKosPorts != "master":
        tag += f"-kp{snapshotKosPorts.lower()}"
    if snapshotGLdc != "master":
        # Only extract the ddmmyy part (as it is a branch, it sould be initially release/ddmmyy. E.g release/10JAN24)
        tag += f"-gl{snapshotGLdc[-7:].lower()}"

    docker_build_command = [
        "docker", "build", 
        f"--build-arg", f"snapshotKos={snapshotKos}", 
        f"--build-arg", f"snapshotKosPorts={snapshotKosPorts}", 
        f"--build-arg", f"snapshotGLdc={snapshotGLdc}", 
        "-t", f"{args.username}/dc-kos-image:{tag}", "./kos-ready/"
    ]
    
    print_settings(args, snapshotKos, snapshotKosPorts, snapshotGLdc,docker_build_command)
    
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