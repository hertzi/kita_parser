#! /usr/bin/env python3
import requests
from lxml.html import fromstring
import coloredlogs
import logging
import threading
import random
import datetime

kita_elements_xpath = '/html/body/div[2]/div/div/div/div[4]/div[2]/div/form/div/table[2]/tr/td/*'
base_url = 'https://www.berlin.de/sen/jugend/familie-und-kinder/kindertagesbetreuung/kitas/verzeichnis/'
free_places_url = base_url + 'FreiePlaetze.aspx'
last_run_results = {}

class Kita(object):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

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
        # elements.append("Adr: " + self.KitaAdresse)
        # elements.append("Link: " + self.Link)
        elements.append("Reg: " + self.Ortsteil)
        # elements.append("Own: " + self.TraegerName)
        elements.append("Reg: " + self.Ortsteil)
        # elements.append("minAge: " + self.Aufnahmealter)
        # elements.append("freeAllAges" + self.PlaetzeBeliebig)
        elements.append("freeUnder3: " + self.PlaetzeUnter3)
        elements.append("freeOver3: " + self.PlaetzeUeber3)
        elements.append("daylyHours: " + str(self.StdTaeglich))
        return ", ".join(elements)

def load_last_run():
    return last_run_results

def save_last_run(kita_list, time):
    global last_run_results
    last_run_results.update({"last_modified":time, "kita_list":kita_list})

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
        last_filtered = filter_kitas(last_run.get("kita_list"))
        currend_filtered = filter_kitas(kitas)
        if last_filtered == currend_filtered:
            logging.info("page updated - but no kitas of interest")
        else:
            for kita in list(currend_filtered.values()):
                logging.info(kita)
            logging.info("kitas(with_free): {}({})".format(len(kitas), len(currend_filtered)))
        return kitas

def run_continuesly():
    seconds = (60*5) + random.randint(60, 300)
    logging.debug("run again in {}s({:0.1f}min)".format(seconds, seconds/60))
    threading.Timer(seconds, run_continuesly).start()
    last_run = load_last_run()
    current_run = find_free_places(last_run)
    if current_run != None:
        save_last_run(current_run, datetime.datetime.now())

def main():
    run_continuesly()

if __name__ == "__main__":
    FORMAT = '%(asctime)s %(levelname)s [%(threadName)s] %(module)s:%(funcName)s\t%(message)s'
    # logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    coloredlogs.install(level='DEBUG', fmt=FORMAT)
    main()