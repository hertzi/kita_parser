# Kita Parser

This script parses the 'open places' page of berlin.de kita

When running continuously it creates a database and compares the results of each run to notify the user about new publications.

TODO:
- [x] persist list of kitas between runs
- [x] add notification channels
- [ ] add filter configuration

## Installation

1. install virtualenv 
2. create a virtual environment
```bash
python3 -m virtualenv venv
```
3. activate virtual environment 
```bash
source ./venv/bin/activate
```
4. install requirements
```bash
python3 -m pip -r requirements.txt
```
5. optional - install service: 
    1. copy kita_parser.service (with sudo) to /etc/serviced/service/
    2. replace \<userName\> with actual user
    3. enable auto start of service and start service
    ```bash
    sudo systemctl enable kita_parser
    sudo systemctl start kita_parser
    ```
    4. get service status 
    ```bash
    sudo systemctl status kita_parser
    ```
