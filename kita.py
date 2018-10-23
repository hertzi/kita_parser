#! /usr/bin/env python3
import requests
from lxml.html import fromstring
import coloredlogs
from logging.handlers import TimedRotatingFileHandler
import logging
import threading
import os
import random
import datetime
import json
import smtplib
from email.mime.text import MIMEText
import argparse


log_file_name = "kita_parser.log"
last_run_file_name = "last_run.json"
kitas_file_template = "kitas_{}.json"
kita_elements_xpath = '/html/body/div[2]/div/div/div/div[4]/div[2]/div/form/div/table[2]/tr/td/*'
base_url = 'https://www.berlin.de/sen/jugend/familie-und-kinder/kindertagesbetreuung/kitas/verzeichnis/'
free_places_url = base_url + 'FreiePlaetze.aspx'
email_config = None

class EmailConfig(object):
    def __init__(self):
        super().__init__()

class Kita(object):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.Link = self.Link.replace(' ', '')

    def add_daily_hours(self, hours):
        hours_list = []
        if type(self.StdTaeglich) != list:
            hours_list.append(self.StdTaeglich)
            self.StdTaeglich = hours_list
        self.StdTaeglich.append(hours)

    # TODO: they are not the same if they have different daily_hours
    def __hash__(self):
        return hash(self.KitaNr)

    def __eq__(self, other):
        return (isinstance(other, Kita) 
            and self.KitaNr == other.KitaNr 
            and self.StdTaeglich == other.StdTaeglich)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        elements = []
        # elements.append("Nr: " + self.KitaNr)
        elements.append("Name: " + self.KitaName)
        elements.append("Adr: " + self.KitaAdresse)
        elements.append("Link: " + self.Link)
        elements.append("Reg: " + self.Ortsteil)
        # elements.append("Own: " + self.TraegerName)
        elements.append("Reg: " + self.Ortsteil)
        # elements.append("minAge: " + self.Aufnahmealter)
        # elements.append("freeAllAges" + self.PlaetzeBeliebig)
        elements.append("freeUnder3: " + self.PlaetzeUnter3)
        elements.append("freeOver3: " + self.PlaetzeUeber3)
        elements.append("daylyHours: " + str(self.StdTaeglich))
        return ", ".join(elements)

class KitaEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, Kita):
            return obj.__dict__

def from_json(json_object):
    if 'KitaNr' in json_object:
        return Kita(**json_object)
    else:
        return json_object

def load_last_run():
    # if file last_run doesnt exist
    if not os.path.isfile(last_run_file_name):
        return {}

    last_run_file = open(last_run_file_name, 'r')
    json_line = json.loads(last_run_file.readline())
    time = json_line["last_modified"]
    last_run_file.close()
    file_name = kitas_file_template.format(time)
    if not os.path.isfile(file_name):
        logging.warn("loading of kitas failed - could not find file {}".format(file_name))
        return {}

    kita_file = open(file_name, 'r')
    kitas = json.JSONDecoder(object_hook = from_json).decode(kita_file.readline())
    kita_file.close()

    return {"last_modified":datetime.datetime.fromtimestamp(time), "kita_list":kitas}


def save_last_run(kita_list, time):
    last_run_file = open(last_run_file_name, 'w')
    run_dict = {}
    run_dict["last_modified"] = time.timestamp()
    print(json.dumps(run_dict), file=last_run_file)
    last_run_file.close()

    kitas = open(kitas_file_template.format(time.timestamp()), 'w')
    print(json.dumps(kita_list, cls=KitaEncoder), file=kitas)
    kitas.close()


def strip_and_add(kita, element, name):
    member = element.attrib[name].split("_")[1].replace('lbl', '').replace('HLink', '')
    kita[member] = element.text_content()

def build_kitas_from_elements(kita_elements):
    kitas = []
    for element in kita_elements:
        # logging.debug(element.tag, element.attrib, element.text_content())
        if element.tag == "a":
            kita = {}
            strip_and_add(kita, element, 'id')
            kita["Link"] = base_url + element.attrib["href"]
            kitas.append(kita)
        elif element.tag == "span":
            kita_id = int(element.attrib["id"].split('_')[-1])
            kita = kitas[kita_id]
            strip_and_add(kita, element, 'id')
    
    kita_objects = {}
    for kita in kitas:
        obj = Kita(**kita)
        if kita_objects.get(obj.KitaNr) != None:
            updated = kita_objects[obj.KitaNr]
            updated.add_daily_hours(obj.StdTaeglich)
            kita_objects[obj.KitaNr] = updated
        else:
            kita_objects[obj.KitaNr] = obj
    return kita_objects

def send_email_notification(text):
    if not email_config.send_notification:
        logging.debug("email notifications are switched off")
        return
    msg = MIMEText(text)
    msg["From"] = email_config.sender
    # msg["To"] = "angeliki.hertzfeldt@gmail.com, rene.hertzfeldt@live.de"
    msg["To"] = ", ".join(email_config.to)
    msg["Subject"] = "kita gefunden"
    smtp = smtplib.SMTP(host=email_config.host, port=email_config.port)
    smtp.starttls()
    smtp.login(email_config.user, email_config.password)
    resp = smtp.send_message(msg)
    smtp.close()


# TODO find filter criterias
def filter_kitas(kitas):
    filtered_kitas = {}
    if kitas == None:
        return filtered_kitas
    for kita in list(kitas.values()):
        if int(kita.PlaetzeUnter3) > 0 and '7 - 9' in kita.StdTaeglich:
            filtered_kitas.update({kita.KitaNr: kita})
    return filtered_kitas

def find_free_places(last_run):
    response = requests.get(free_places_url)

    if response.status_code != 200:
        logging.error("websites response was {}".format(response.status_code))
        return

    doc = fromstring(response.content)
    kita_elements = doc.xpath(kita_elements_xpath)

    if len(kita_elements) == 0:
        logging.warning("possible error - no kita elements found")
        return

    kitas = build_kitas_from_elements(kita_elements)

    if last_run != {} and kitas == last_run["kita_list"]:
        logging.info("no changes - pages last detected update {}".format(last_run["last_modified"]))
        return
    else:
        if last_run != {}:
            new_kitas = dict(kitas.items() - last_run.get("kita_list").items())
        else:
            new_kitas = kitas
        if len(new_kitas) == 0:
            logging.info("page update - but kitas have just been removed")
        else:
            new_kitas_filtered = filter_kitas(new_kitas)
            if len(new_kitas_filtered) == 0:
                logging.info("page updated - but no kitas of interest")
            else:
                kitas_string = ""
                for kita in new_kitas_filtered.values():
                    logging.info(kita)
                    kitas_string += str(kita) + "\n"
                send_email_notification(kitas_string)
            logging.info("kitas(with_free): {}({})".format(len(kitas), len(new_kitas_filtered)))
        return kitas

def run_continuesly():
    seconds = (60*5) + random.randint(60, 300)
    logging.debug("run again in {}s({:0.1f}min)".format(seconds, seconds/60))
    threading.Timer(seconds, run_continuesly).start()
    last_run = load_last_run()
    current_run = find_free_places(last_run)
    if current_run != None:
        save_last_run(current_run, datetime.datetime.now())

def set_email_config(args):
    global email_config
    email_config = EmailConfig()
    email_config.send_notification = args.send_notification
    email_config.user = args.email_user
    email_config.password = args.email_password
    email_config.host = args.email_host
    email_config.port = args.email_port
    email_config.sender = args.email_from
    email_config.to = args.email_to


def main():
    run_continuesly()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="parsing berlin.de for new kita places - sends notification if something of interest pops up.")
    parser.add_argument("-n", "--send_notification", help="set true to send emai notifications - default False", type=bool, default=False)
    parser.add_argument("--email_user", "-u", help="gmail address to send notifications from")
    parser.add_argument("--email_password", "-p", help="gmail password")
    parser.add_argument("--email_host", "-H", help="email server different from gmail", default="smtp.gmail.com")
    parser.add_argument("--email_port", "-P", help="email server port - default 587", default=587, type=int)
    parser.add_argument("--email_from", "-f", help="gmail address to send notifications from")
    parser.add_argument("--email_to", "-t", help="email address(es) to send notifications to", action='append', default=[])

    args = parser.parse_args()
    set_email_config(args)
    
    #logs
    FORMAT = '%(asctime)s %(levelname)s [%(threadName)s] %(module)s:%(funcName)s\t%(message)s'
    # logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    coloredlogs.install(level='INFO', fmt=FORMAT)
    file_handler = TimedRotatingFileHandler(log_file_name, when='d')
    file_handler.setFormatter(logging.Formatter(FORMAT))
    logging.getLogger().addHandler(file_handler)
    main()