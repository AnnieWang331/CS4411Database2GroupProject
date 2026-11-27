# Recommended for Peer-Reviewers: Instructions for running our project in the school lab computer 

## Overview
We reconigize that everyone's pc setup, enviourments and experiences are all different. In an effort to make sure that at least one instruction gerrented to work for all student, we made this `step-by-step` guild on how to setup our project in the computers located in the lab room at **Middlesex College 2nd Floor Room 244**. 

This project should be run-able if a student follow the exact `step-by-step` guild with no friction at all. 

## Instruction: 

1. **Open a bash terminal** \
Two ways to do this, choose which ever one is most comfortable to you. 
    1. Open a bash terminal with `Ctrl + Alt + T` 
    2. Make a new folder called `CS4411`
        ```
        mkdir -p ~/CS4411
        ```
    3. Change the directory to the newly made folder
        ```
        cd ~/CS4411
        ```
    4. Your bash terminal's new line should output `[student id]@pcr-[lab pc number]:~/CS4411$ `. \
    **Do not preceed to next step if this is not true.**

    Alterninatively, open a bash terminal in **Visual Studio Code**: 
    1. Open the `Files` app. 
    2. Make a new folder called `CS4411` 
    3. Open `Visual Studio Code` 
    4. On the top tool bar of `Visual Studio Code`, go into `File` -> `Open Folder...` and choose the new folder you just created. \
    It should be under `/home/[student_id]/CS4411`.
    5. Once in the folder, the `Explorer` view should say `CS4411` and nothing else. \
    Note: if we don't spot a `Explorer` view, open it by selecting `View` -> `Explorer` on the top tool bar of `Visual Studio Code`. 
    6. Open a terminal by going into `Terminal` -> `New Terminal` on the top tool bar of `Visual Studio Code`. 
    7. The newly openned terminal should output `[student id]@pcr-[lab pc number]:~/CS4411$`. \
    **Do not preceed to next step if this is not true.** 

2. **Clone the repo** \
Note: from this point on, any command that needs to be ran are pasted and executed into the bash terminal we just openned. 
    ```
    git clone https://github.com/AnnieWang331/CS4411Database2GroupProject.git
    ```

3. **Check Python Version** \
It should be pre-installed, still, best practice to check it.
    ```
    python3 -V
    ```
    This should output `Python 3.14.4`

4. **Setup Virtual environment**
    ```
    cd ~/CS4411/CS4411Database2GroupProject/
    python3 -m venv --without-pip .venv
    source .venv/bin/activate
    .venv\Scripts\Activate.ps1
    ```
    The newline should output `(.venv) [student id]@pcr-[lab pc number]:~/CS4411/CS4411Database2GroupProject$ `.
    ```
    wget https://bootstrap.pypa.io/get-pip.py
    python3 get-pip.py
    pip install -r requirements-dev.txt
    ```
5. **Check Java version** \
Note that we're setting up DynamoDB Local without Docker because we do not have sudo pervilages on the lab PCs.
    ```
    java -version
    ```
    Java version must be **Java 17** or above. \
    If Java version is at **Java 17** or newer, preceed to the next step. \
    Else, run these commands to setup Java 17: 
    ```
    curl -s "https://get.sdkman.io" | bash
    source "$HOME/.sdkman/bin/sdkman-init.sh"
    sdk install java 17.0.13-tem
    ```
    Check Jave version again: 
    ```
    java -version
    ```
    It should output something like this: 
    ```
    openjdk version "17.0.13" 2024-10-15
    OpenJDK Runtime Environment Temurin-17.0.13+11 (build 17.0.13+11)
    OpenJDK 64-Bit Server VM Temurin-17.0.13+11 (build 17.0.13+11, mixed mode, sharing)
    ```
    The important take away is that openjdk version, e.i. Java version is 17 or above. 
5. Setup for DynamoDB Local
    ```
    mkdir -p ~/CS4411/dynamodb_local && cd ~/CS4411/dynamodb_local
    wget https://d1ni2b6xgvw0s0.cloudfront.net/v3.x/dynamodb_local_latest.zip
    jar -xf dynamodb_local_latest.zip
    ls
    ```
    `ls` should output:
    ```
    DynamoDBLocal.jar  DynamoDBLocal_lib  LICENSE.txt  README.txt  THIRD-PARTY-LICENSES.txt  dynamodb_local_latest.zip  dynamodb_local_latest.zip.1
    ```
    **Do not perceed if this doesn't match your output.** \
6. Run DynamoDB Local
    ```
    java "-Djava.library.path=./DynamoDBLocal_lib" -jar DynamoDBLocal.jar -inMemory -sharedDb
    ```
7. Open a new terminal and setup enviourment paths
    ```
    export DYNAMODB_ENDPOINT_URL="http://localhost:8000"
    ```
8. Create the table and add demo data
    ```
    python scripts/create_table.py
    python scripts/seed.py
    ```
9. Run the tests
    ```
    export REQUIRE_DYNAMODB_LOCAL="1"; pytest
    ```
10. Run the Backend
    ```
    python scripts/serve_local.py
    ```
11. Run the Frontend
    ```
    cd ~/CS4411/CS4411Database2GroupProject
    python3 -m http.server 8080 -b 127.0.0.1 -d web
    ```

Questions? Email `wwang939@uwo.ca` for setup support. 
TODO: add some gitignore items for the new setup. 
