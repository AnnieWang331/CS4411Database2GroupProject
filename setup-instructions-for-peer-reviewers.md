# Recommended for Peer-Reviewers: Instructions for running our project in the school lab computer 

## Overview
We recognize that everyone's PC setup, environment and experiences are different. In an effort to make sure that at least one set of instruction guaranteed to work for all student, we made this `step-by-step` guild for setting up the project on the lab computers located at **Middlesex College 2nd Floor Room 244**. 

Following this specific set of instruction on the lab PCs should make the setup friction-less. 
A [YouTube video](https://www.youtube.com/watch?v=tu6CemJ2Jz8) demonstrating these instruction on one of the lab PC also exists: <https://www.youtube.com/watch?v=tu6CemJ2Jz8>

## Instruction: 

1. **Open a Bash Terminal** 
    1. Open a bash terminal with `Ctrl + Alt + T` 
    2. Make a new folder called `CS4411` and cd into the newly made folder \
        **Command Input:**
        ```
        mkdir -p ~/CS4411 && cd ~/CS4411
        ```
        Your bash terminal's new line should output `[student id]@pcr-[lab pc number]:~/CS4411$ `. \
        **Sample Output:**
        ```
        [student id]@pcr-[lab pc number]:~/CS4411$ 
        ```
        **Do not proceed to next step if this is not true.**

2. **Clone the Repository** \
Note: from this point on, any command that needs to be ran are pasted and executed into the bash terminal. \
**Command Input:**
    ```
    git clone https://github.com/AnnieWang331/CS4411Database2GroupProject.git
    ```
    **Sample Output:**
    ```
    Cloning into 'CS4411Database2GroupProject'...
    remote: Enumerating objects: 661, done.
    remote: Counting objects: 100% (216/216), done.
    remote: Compressing objects: 100% (121/121), done.
    remote: Total 661 (delta 99), reused 175 (delta 86), pack-reused 445 (from 1)
    Receiving objects: 100% (661/661), 6.04 MiB | 22.35 MiB/s, done.
    Resolving deltas: 100% (211/211), done.
    ```
3. **Check Python Version** \
Python should be pre-installed, still, best practice to check it's version. \
**Command Input:**
    ```
    python3 -V
    ```
    This should output `Python 3.14.4`, any version above `Python 3.12` is okay. \
    **Sample Output:**
    ```
    Python 3.14.4
    ```
4. **Setup Virtual Environment** \
**Command Input:**
    ```
    cd ~/CS4411/CS4411Database2GroupProject/
    python3 -m venv --without-pip .venv
    source .venv/bin/activate
    .venv\Scripts\Activate.ps1
    ```
    The newline should start with `(.venv)`.\
    **Sample Output:**
    ```
    (.venv) [student id]@pcr-[lab pc number]:~/CS4411/CS4411Database2GroupProject$ 
    ```
    Continue setup in the virtual environment: \
    **Command Input:**
    ```
    wget https://bootstrap.pypa.io/get-pip.py
    python3 get-pip.py
    pip install -r requirements-dev.txt
    ```
    **Sample Output:**
    ```
    --2026-11-27 17:04:51--  https://bootstrap.pypa.io/get-pip.py
    Resolving bootstrap.pypa.io (bootstrap.pypa.io)... 146.75.80.175, 2a04:4e42:84::175
    
    ... [More output here] ...

    get-pip.py          100%[===================>]   2.29M  --.-KB/s    in 0.07s   

    ... [More output here] ...

    Successfully installed PyYAML-6.0.4 annotated-types-0.8.0 attrs-26.1.0 aws-sam-translator-1.118.0 awscrt-0.38.0 boto3-1.43.114 botocore-1.43.127 cfn-lint-1.48.1 contourpy-1.4.0 cycler-0.12.1 fonttools-4.69.1 iniconfig-2.3.1 jmespath-1.1.0 jsonpatch-1.48 jsonpointer-3.12 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 kiwisolver-1.5.1 matplotlib-3.11.2 mpmath-1.3.0 networkx-3.7 numpy-2.5.5 packaging-26.4 pillow-13.0.0 pluggy-1.7.0 pydantic-2.13.5 pydantic-core-2.46.5 pygments-2.21.0 pyparsing-3.3.3 pytest-9.1.1 python-dateutil-2.9.0.post0 referencing-0.37.0 regex-2026.11.25 rpds-py-2026.9.1 ruff-0.17.1 s3transfer-0.19.3 six-1.17.0 sympy-1.14.0 typing-inspection-0.4.5 typing_extensions-4.16.0 urllib3-2.8.0 websockets-17.4
    ```
5. **Check Java version** \
Note that we're setting up DynamoDB Local without Docker because we do not have sudo privileges on school lab PCs. \
**Command Input:**
    ```
    java -version
    ```
    **Sample Output:**
    ```
    openjdk version "11.0.33.1" 2026-11-17
    OpenJDK Runtime Environment (build 11.0.33.1+1-post-1ubuntu1-26.04.1-Ubuntu)
    OpenJDK 64-Bit Server VM (build 11.0.33.1+1-post-1ubuntu1-26.04.1-Ubuntu, mixed mode, sharing)
    ```
    Java version must be **Java 17** or above. \
    If Java version is at **Java 17** or newer, preceed to the next step. \
    Else, run these commands to setup Java 17. \
    **Command Input for Java 17 setup:**
    ```
    curl -s "https://get.sdkman.io" | bash
    source "$HOME/.sdkman/bin/sdkman-init.sh"
    sdk install java 17.0.13-tem
    ```
    **Sample Output:**
    ```
    sdk install java 17.0.13-tem

    ... [More output here] ...

    Looking for a previous installation of SDKMAN...
    Checking Bash version...
    Looking for unzip...

    ... [More output here] ...

    * Downloading...
    ######################################################################## 100.0%

    ... [More output here] ...

    Done repackaging...

    Installing: java 17.0.13-tem
    Done installing!


    Setting java 17.0.13-tem as default.
    ```

    Check Jave version again after installation. \
    **Command Input:**
    ```
    java -version
    ```
    **Sample Output:**
    ```
    openjdk version "17.0.13" 2024-10-15
    OpenJDK Runtime Environment Temurin-17.0.13+11 (build 17.0.13+11)
    OpenJDK 64-Bit Server VM Temurin-17.0.13+11 (build 17.0.13+11, mixed mode, sharing)
    ```
    The important take away is that openjdk version (i.e. Java version) is 17 or above. 
6. **Setup for DynamoDB Local**
    **Command Input:**
    ```
    mkdir -p ~/CS4411/dynamodb_local && cd ~/CS4411/dynamodb_local
    wget https://d1ni2b6xgvw0s0.cloudfront.net/v3.x/dynamodb_local_latest.zip
    jar -xf dynamodb_local_latest.zip
    ls
    ```
    **Sample Output for `ls`:**
    ```
    DynamoDBLocal.jar  DynamoDBLocal_lib  LICENSE.txt  README.txt  THIRD-PARTY-LICENSES.txt  dynamodb_local_latest.zip  dynamodb_local_latest.zip.1
    ```
    **Do not proceed if this doesn't match your output.** 
7. **Run DynamoDB Local** \
**Command Input:**
    ```
    java "-Djava.library.path=./DynamoDBLocal_lib" -jar DynamoDBLocal.jar -inMemory -sharedDb
    ```
    **Sample Output:**
    ```
    Initializing DynamoDB Local with the following configuration:
    Port:	8000
    InMemory:	true
    Version:	3.3.1
    DbPath:	null
    SharedDb:	true
    shouldDelayTransientStatuses:	false
    CorsParams:	null
    ```
8. **Open a New Terminal and Setup Environment Variables** \
**Command Input:**
    ```
    cd ~/CS4411/CS4411Database2GroupProject/
    source .venv/bin/activate
    export DYNAMODB_ENDPOINT_URL="http://localhost:8000"
    ```
    There's no sample output. These commands doesn't print anything to console. 
9. **Create the Table and Add Demo Data** \
**Command Input:**
    ```
    python3 scripts/create_table.py
    python3 scripts/seed.py
    ```
    **Sample Output:**
    ```
    Room e84d0e1e5ee740c48d2a86ddcb12bff7  code MY3UKS  topic: How should we index a classroom brainstorm board?
    [3 votes] Annie: Keep every room in one partition so one Query loads the board
        - Sachin: And it avoids joins entirely
    [2 votes] Roah: Store vote counts on the idea with an atomic counter
    [1 vote] Sachin: Use TTL so rooms clean themselves up after class
    [0 votes] Haadi: Push new ideas to clients with DynamoDB Streams
        - Annie: Streams plus a WebSocket API Gateway
    ```
10. **Run Tests** \
**Command Input:**
    ```
    export REQUIRE_DYNAMODB_LOCAL="1"; pytest
    ```
    **Sample Output:**
    ```
    ============================= test session starts ==============================
    platform linux -- Python 3.14.4, pytest-9.1.1, pluggy-1.7.0
    rootdir: /home/wwang939/CS4411/CS4411Database2GroupProject
    configfile: pyproject.toml
    testpaths: tests
    collected 148 items                                                            

    tests/brainstorm/test_api.py ...............................             [ 20%]


    ... [More output here] ...


    tests/scripts/test_ttl_demo.py ...                                       [100%]

    ============================= 148 passed in 11.38s =============================
    ```
11. **Run Backend** \
**Command Input:**
    ```
    python scripts/serve_local.py
    ```
    **Sample Output:**
    ```
    INFO:websockets.server:server listening on 127.0.0.1:3001
    ```
12. **Open a New Terminal and Run Frontend** \
**Command Input:**
    ```
    cd ~/CS4411/CS4411Database2GroupProject
    python3 -m http.server 8080 -b 127.0.0.1 -d web
    ```
    **Sample Output:**
    ```
    Serving HTTP on 127.0.0.1 port 8080 (http://127.0.0.1:8080/) ...
    ```

Questions? Email `wwang939@uwo.ca` for support. 
