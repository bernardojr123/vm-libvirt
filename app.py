import os
import libvirt
import random
import uuid

from xml.dom import minidom
from shutil import copy2

from flask import Flask, render_template, jsonify
from flask_wtf import FlaskForm
from flask_bootstrap import Bootstrap
from wtforms import StringField, IntegerField
from wtforms.validators import InputRequired, IPAddress

# virt-install --name=linuxconfig-vm \
# --addpkg acpid \
# --vcpus=1 \
# --memory=1024 \
# --cdrom=/home/bernardo/PycharmProjects/CriadorVM/SOs/ubuntu-18.04.1-desktop-amd64.iso \
# --disk size=5 \
# --os-variant=debian8

app = Flask(__name__)
Bootstrap(app)

debug = False
app.secret_key = "jaisdoijdsa"

conn = libvirt.open("qemu:///system")
domains = conn.listAllDomains()
uuidx = '528cd396-112e-11e9-9f25-e0d55e453555'


def get_xml_from_domain(domain):
    data = domain.XMLDesc()
    xml = minidom.parseString(data)
    return xml


def get_mac_from_domain(domain):
    xml = get_xml_from_domain(domain)
    node = xml.getElementsByTagName('mac')
    mac = node[0].attributes['address'].value
    return mac


def random_mac():
    mac = [0x00, 0x16, 0x3e,
           random.randint(0x00, 0x7f),
           random.randint(0x00, 0xff),
           random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x: "%02x" % x, mac))


def generate_unique_mac():
    mac = random_mac()
    macs = map(get_mac_from_domain, domains)
    while mac in macs:
        mac = random_mac()
    return mac


def update_network_settings(mac, ip):
    template_ip = f'<host mac="{mac}" ip="{ip}"/>'
    network = conn.networkLookupByName("default")
    result = network.update(libvirt.VIR_NETWORK_UPDATE_COMMAND_ADD_FIRST, libvirt.VIR_NETWORK_SECTION_IP_DHCP_HOST, -1,
                            template_ip)
    return result


def clone_harddisk(doc, hostname):
    disk = doc.getElementsByTagName("disk")[0]
    source = disk.getElementsByTagName("source")[0]
    folder = source.attributes['file'].value
    filename = folder.split('/').pop()
    extension = filename.split('.').pop()

    filename = f'{hostname}.{extension}'
    img_path = os.path.join(os.getcwd(), "images")
    path = os.path.join(img_path, f"{filename}")
    copy2(folder, path)
    source.attributes['file'].value = path


class VirtForm(FlaskForm):
    hostname = StringField('Hostname:', validators=[InputRequired()])
    memory = IntegerField('Memory:', validators=[InputRequired()])
    ipv4 = StringField('IPv4:', validators=[InputRequired(), IPAddress(ipv4=True, ipv6=False)])
    cpu = IntegerField("CPU:", validators=[InputRequired()])


def clone_it(document, form):
    xml = minidom.parseString(document)
    host_name = form.hostname.data
    memory = form.memory.data
    cpu = form.cpu.data
    ip = form.ipv4.data

    clone_harddisk(xml, host_name)
    # new uuid
    uuidx = str(uuid.uuid1())
    tag = xml.getElementsByTagName("uuid")[0]
    tag.firstChild.nodeValue = uuidx
    # new name
    tag = xml.getElementsByTagName("name")[0]
    tag.firstChild.nodeValue = host_name
    # new mem
    correct_mem = memory * 1024
    tag = xml.getElementsByTagName("memory")[0]
    tag.firstChild.nodeValue = correct_mem
    tag = xml.getElementsByTagName("currentMemory")[0]
    tag.firstChild.nodeValue = correct_mem
    # new cpu
    tag = xml.getElementsByTagName("vcpu")[0]
    tag.firstChild.nodeValue = cpu
    # # network
    # mac = generate_unique_mac()
    # tag = xml.getElementsByTagName("mac")[0]
    # tag.attributes["address"].value = mac
    # update_network_settings(mac, ip)

    result = xml.toxml()
    return result


@app.route('/form', methods=['GET', 'POST'])
def form():
    form = VirtForm()
    if form.validate_on_submit():
        domain = conn.lookupByName("linuxconfig-vm")
        state, reason = domain.state()
        print(f"Domain state {state}, reason {reason}")
        if state == libvirt.VIR_DOMAIN_RUNNING:
            domain.suspend()
            while domain.state()[0] != libvirt.VIR_DOMAIN_PAUSED:
                pass

        document = domain.XMLDesc()
        new_xml = clone_it(document, form)

        clone = conn.defineXML(new_xml)
        clone.create()
        domain.resume()

        result = {}
        result['hostname'] = form.hostname.data
        result['ipv4'] = form.ipv4.data
        result["memory"] = {"MB": form.memory.data}
        result["cpu"] = form.cpu.data
        return jsonify(result)
    return render_template('form.html', form=form)


@app.route('/')
def hello_world():
    return 'Pagina inicial'


if __name__ == '__main__':
    app.run(debug=debug, host='0.0.0.0')
