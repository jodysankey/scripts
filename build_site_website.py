#!/usr/bin/python3
# -*- coding: utf-8 -*-
#========================================================
# Python script to build a web version of the Site
# management XML in user friendly HTML
# 
# All data is based on the XML files in the location
# specified below, and output to the location below
#========================================================
# Copyright Jody M Sankey 2011
#========================================================
# $HeadURL$
# Last $Author: jody $
# $Revision: 720 $
# $Date: 2009-10-30 18:12:20 -0500 (Fri, 30 Oct 2009) $
#========================================================
# AppliesTo: linux
# AppliesTo: oberon
# RemoveExtension: True
#========================================================
# Possible Improvements:
# Colorize output of Python
# Colorize output of bash comments
# Selectively pull in deployed files where available
#   and where permissions are appropriate e.g. scripts
#========================================================

import os
import socket

#Override to the read/write site for easy development
if socket.gethostname().lower() in ("vicki", "debbie"):
    os.environ["SITEPATH"] = "/mnt/site-dev"

import sys
import subprocess

from datetime import datetime
import svnauthorization
import tagwriter
import sitemgt
from sitemgt.paths import SITE_XML_FILE, WEB_OUTPUT_DIR 


auth = svnauthorization.SvnAuthorization()

class BodyTagWriter(tagwriter.TagWriter):
    """Extends simple tag writer to open and close a standard data html"""

    def __init__(self, filename, class_name, parent_title):
        super().__init__(filename)
        self.writeOrphan('!DOCTYPE', 'html')
        self.open('html')
        self.writeOrphan('link', 'rel="stylesheet" href="../static/style.css" typename="text/css"')
        self.writeOrphan('meta', 'http-equiv="Content-Type" content="text/html;charset=utf-8"')
        
        attr = ""
        if class_name is not None:
            attr += ' class="{}"'.format(class_name)
        if parent_title is not None:
            json = "{{'title': '{}', 'date': '{}'}}".format(
                parent_title, datetime.today().strftime("Page generated at: %Y-%m-%d %H:%M"))
            attr += ' onload="parent.title.postMessage(JSON.stringify({}), \'*\');"'.format(json)
        self.open('body',attr)
    
    def __del__(self):
        if self.depth()<2: print("Tried to close too many tags in :" + self.filename)
        self.close()
        self.close()
        super().__del__()

    def writeAttributePara(self, obj, english_name,attr_name):
        if hasattr(obj, attr_name):
            if english_name is None:
                self.writeText('<p>{}</p>'.format(getattr(obj, attr_name)))
            else:
                self.writeText('<p><b>{} :</b> {}</p>'.format(
                       english_name, getattr(obj, attr_name)))

    def writeLink(self, text, destination, targetFrame=None):
        if targetFrame is None:
            self.write('a', 'href="{}"'.format(destination), text)
        else:
            self.write('a','href="{}" target="{}"'.format(destination, targetFrame), text)

    def writeObjectLink(self, siteObject, text=None, targetFrame=None):
        if text is None:
            text = siteObject.name
        self.writeLink(text=text, destination=siteObject.htmlName(), targetFrame=targetFrame)

    def writeNestedObjectLink(self, tag, attributes, siteObject, text=None, targetFrame=None):
        self.open(tag, attributes)
        self.writeObjectLink(siteObject, text, targetFrame)
        self.close()

    def writeSystemRequirementHeader(self):
        self.writeText('<tr><th>UID</th><th>Text</th><th>Importance</th><th>Verification</th><th>Status</th></tr>')
    def writeSystemRequirementRow(self, system_requirement, generateRowTag=True):
        if generateRowTag: self.open('tr')
        cls = system_requirement.htmlClass()
        self.writeNestedObjectLink('td', cls, system_requirement)
        self.write('td', cls, system_requirement.text)
        self.write('td', cls, system_requirement.importance_text)
        self.write('td', cls, system_requirement.verification.description)
        self.write('td', cls, system_requirement.status)
        if generateRowTag: self.close() #TR


    def writeAutomaticCheckHeader(self):
        self.writeText('<tr><th>Automatic Check</th><th>Last Run</th><th>Outcome</th><th>Description</th></tr>')
    def writeAutomaticCheckRow(self, automatic_check, generateRowTag=True):
        if generateRowTag: self.open('tr')
        cls = automatic_check.htmlClass()
        self.writeNestedObjectLink('td', cls, automatic_check)
        if automatic_check.lastOutcome():
            self.writeCheckOutcomeRow(automatic_check.lastOutcome(), cls, False)
        else:
            self.write('td', cls, "N/A")
            self.write('td', cls, "N/A")
            self.write('td', cls, automatic_check.result_error
                       if hasattr(automatic_check, 'result_error') else 'UNKNOWN')
        if generateRowTag: self.close() #TR

    def writeCheckOutcomeHeader(self):
        self.writeText('<tr><th>Run</th><th>Outcome</th><th>Description</th></tr>')
    def writeCheckOutcomeRow(self, outcome, htmlClass=None, generateRowTag=True):
        if generateRowTag: self.open('tr')
        if htmlClass is None:
            htmlClass = ' class="{}"'.format('good' if outcome.success else 'fail')
        self.write('td', htmlClass, outcome.timestamp)
        self.write('td', htmlClass, outcome.outcome())
        self.write('td', htmlClass, outcome.description)
        if generateRowTag: self.close() #TR
        
    #TODO: Consider adding more of these object specific write functions to simplify the page generators



        
def makeListHtml(hdg_iter_pfx, object_description, output_base):
    """Creates an html file to list the specified elements"""
    list_filename = os.path.join(WEB_OUTPUT_DIR, "list_" + output_base)
    wt = BodyTagWriter(list_filename, 'list', parent_title = None) 
    
    wt.open('p','')
    wt.writeLink(text='All ' + object_description, destination='all_' + output_base, targetFrame='data')
    wt.close()
    for (heading, it) in hdg_iter_pfx:
        wt.write('h3', '', heading)
        if type(it) == type(dict()):
            for k in sorted(it.keys()):
                wt.writeNestedObjectLink('p', '', it[k], None, 'data')
        else:
            for v in it:
                wt.writeNestedObjectLink('p', '', v, None, 'data')


def makeSummariesHtml(master_hdg, hdg_dict_att_titles_pfx, output_base):
    """Creates an html file to summarizes state of the specified elements"""
    summary_filename = os.path.join(WEB_OUTPUT_DIR, "all_" + output_base)
    wt = BodyTagWriter(summary_filename, None, master_hdg) 
    
    for (heading, dic, attributes, titles) in hdg_dict_att_titles_pfx:
        wt.write('h3', '', heading)
        wt.open('table')
        wt.open('tr')
        wt.write('th','','Name')
        for title in titles:
            wt.write('th','',title)
        wt.write('th','','Requirements')
        wt.close()  #TR
        for ob_name in sorted(dic.keys()):
            ob = dic[ob_name]
            wt.open('tr')
            wt.writeNestedObjectLink('td',ob.htmlClass(),ob)
            for att in attributes:
                wt.write('td', ob.htmlClass(), getattr(ob, att) if hasattr(ob,att) else '&nbsp;')
            wt.open('td',ob.htmlClass())
            if hasattr(ob,'requirements') and len(ob.requirements)>0:
                for uid in sorted(ob.requirements.keys()):
                    wt.writeObjectLink(ob.requirements[uid])
            else:
                wt.writeText("&nbsp;")
            wt.close()  #TD
            wt.close()  #TR
        wt.close()      #Table


def makeCapabilitySummariesHtml(capabilities):
    """Creates an html file to summarizes all capabilities. Two layer table requires unique code"""
    summary_filename = os.path.join(WEB_OUTPUT_DIR, "all_Capabilities.html")
    wt = BodyTagWriter(summary_filename, None, "All Capabilities") 
    
    # Gather the current maximums of each index (TODO: move into sitedescription)
    max_sys = max_host = max_user = 0
    for cap in capabilities:
        for srq in cap.requirement_list:
            max_sys = max(max_sys, srq.uidNumber())
            for arq in srq.actor_requirement_list:
                if arq.uid[0] == "U":
                    max_user = max(max_user, arq.uidNumber())
                elif arq.uid[0] == "H":
                    max_host = max(max_host, arq.uidNumber())

    wt.write("p", "", ("Next System requirement <b>S{:03}</b>, Host requirement <b>H{:03}</b>,"
             + " User requirement <b>U{:03}</b>").format(max_sys + 1, max_host + 1, max_user + 1))
    wt.open('table')
    wt.writeText('<tr><th colspan="2">Capability</th><th colspan="5">System Requirement</th></tr>')
    wt.writeText('<tr><th>Title</th><th>Status</th><th>UID</th><th>Text</th><th>Importance</th><th>Verification</th><th>Status</th></tr>')
    
    #TODO: Move counts of each status into sitedescription
    status_to_classcount = {}
    
    for cap in capabilities:
        wt.open('tr')
        row_count = max(1,len(cap.requirement_list))
        wt.writeNestedObjectLink('td',cap.htmlClass() + ' rowspan="{}"'.format(row_count),cap)
        wt.write('td',cap.htmlClass() + ' rowspan="{}"'.format(row_count),cap.status)
        if len(cap.requirement_list)==0:
            wt.write('td','hspan="5"','No system requirements')
            wt.close()
        else:
            for req in cap.requirement_list:
                if req is not cap.requirement_list[0]: wt.open('tr')
                wt.writeSystemRequirementRow(req, generateRowTag=False)
                wt.close() #Row
                if req.status not in status_to_classcount.keys():
                    status_to_classcount[req.status] = [req.htmlClass(), 1]
                else:
                    status_to_classcount[req.status][1] += 1
    wt.close() #Table

    wt.write('p','',' ')
    wt.open('table')
    wt.writeText('<tr><th>Status</th><th>Proportion</th></tr>')
    total = sum([v[1] for v in status_to_classcount.values()])
    for item in sorted(status_to_classcount.items(), key=lambda x: x[1][1], reverse=True):
        wt.open('tr')
        wt.write('td',item[1][0], item[0])
        wt.write('td',item[1][0], "{:.1f}%".format((item[1][1] / total) * 100.0))
        wt.close() #Row
    wt.close() #Table


def makeActorHtml(actor,english,is_group):
    """Creates an html file for the specified actor"""
    wt = BodyTagWriter(os.path.join(WEB_OUTPUT_DIR,actor.htmlName()),None, english + " : " + actor.name) 

    #Basic attributes
    wt.write('h2','','Basics')
    if actor.type == 'host':
        wt.writeAttributePara(actor, 'IP Address','ip_address')
        wt.writeAttributePara(actor, 'Purpose', 'purpose')
        wt.writeAttributePara(actor, 'Operating System','os')
        wt.writeAttributePara(actor, 'Last Status', 'status_date')
    elif actor.type == 'user':
        wt.writeAttributePara(actor, 'Type', 'account_type')
        wt.writeAttributePara(actor, 'e-mail','email')        
    else:
        wt.writeAttributePara(actor, 'Description', 'description')

    #Either members of a group, or groups of a member
    if is_group:
        wt.write('h2','','Members')
        for k in sorted(actor.members.keys()):
            wt.writeNestedObjectLink('p','',actor.members[k])
    else:
        wt.write('h2','','Groups')
        if actor.groups:
            for k in sorted(actor.groups.keys()):
                wt.writeNestedObjectLink('p','',actor.groups[k])
        else:
            wt.write('p', '', '{} is not a member of any groups'.format(actor.name))

    #Build responsibility table
    responsibilities = actor.responsibilities
    if not is_group:
        for group in actor.groups.values():
            responsibilities.update(group.responsibilities)
    if responsibilities:
        wt.write('h2','','Responsibilities')
        wt.open('table')
        wt.writeText('<tr><th>Capability</th><th>Target</th><th>Description</th><th>Rationale</tr>')
        for rk in sorted(responsibilities.keys()):
            rsp = responsibilities[rk]
            wt.open('tr')
            wt.writeNestedObjectLink('td','',rsp.capability)
            wt.write('td','', rsp.actor.name)
            wt.write('td','', rsp.description)
            wt.write('td','', rsp.rationale if hasattr(rsp,'rationale') else "&nbsp;")
            wt.close()
        wt.close()

    #Build requirements tables
    requirements = actor.requirements
    if actor.type == 'host':
        hosts = {actor.name:actor}
    elif actor.type == 'hostgroup':
        hosts = actor.members
    else:
        hosts = dict()
    
    if not is_group:
        for group in actor.groups.values():
            requirements.update(group.requirements)
    if requirements:
        wt.write('h2','','Requirements')
        wt.open('table')
        wt.open('tr')
        wt.writeText('<th>UID</th><th>Site Level Status</th><th>Target</th><th>Text</th><th>Supports</th>')
        for host_name in sorted(hosts.keys()):
            wt.write('th','','Software' if len(hosts)==1 else host_name)
        wt.close()
        
        for ark in sorted(requirements.keys()):
            ar = requirements[ark]
            wt.open('tr')
            wt.write('a','name="{}"'.format(ar.uid))

            normal_class =  ar.htmlClass() if actor is ar.actor else 'class="unknown"'
            # Only hyperlink to the real owner if its not us
            if(actor is ar.actor):
                wt.write('td',normal_class, ark)
            else:
                wt.writeNestedObjectLink('td',normal_class,ar,ark)
            wt.write('td',normal_class, ar.status)
            wt.write('td',normal_class, ar.actor.name)
            wt.write('td',normal_class, ar.text)
            wt.open('td',normal_class)
            for srk in sorted(ar.system_requirements.keys()):
                sr = ar.system_requirements[srk]
                wt.writeObjectLink(sr,sr.uid)
            wt.close()
            for hn in sorted(hosts.keys()):
                h = hosts[hn] 
                wt.open('td','class="container"')
                wt.open('table','class="subtable"')
                for depl in [d for d in h.expected_deployments.values() if ar in d.primary_requirements.values()]:
                    wt.writeText('<tr><td class="{}"><a href="{}">{}</a></td></tr>'.format(
                        depl.functionalHealth(),depl.component.htmlName(),depl.component.name))
                wt.close(2)
            wt.close()
        wt.close()

    #Report whether any upgrades are necessary
    if(hasattr(actor,'upgradable_packages') and len(actor.upgradable_packages)>0):
        wt.write('h2','','{} Software Packages Require Upgrade!'.format(len(actor.upgradable_packages)))
        wt.write('p','','As at {}'.format(actor.status_date))
    
    
    if(hasattr(actor,'expected_deployments')):

        #Split expected components by type (i.e. Application/File/Script)
        component_sets = {} 
        component_sets['Applications'] = sorted([d for d in actor.expected_deployments.values() if 
                                          d.component.type.endswith('application')], key=lambda depl: depl.component.name)
        component_sets['Scripts']     = sorted([d for d in actor.expected_deployments.values() if 
                                          d.component.type == 'script'],
                                         key=lambda depl: depl.locationDescription())
        component_sets['Files']       = sorted([d for d in actor.expected_deployments.values() if 
                                          d.component.type.endswith('file')], key=lambda depl: depl.locationDescription())

        for component_set in sorted(component_sets.keys()):
            wt.write('h2','','Expected ' + component_set)
            if len(component_sets[component_set]) == 0:
                wt.write('p','','No documented ' + component_set.lower())
            else:
                wt.open('table')
                wt.writeText('<tr><th>Name</th><th>Type</th><th>Location</th><th>Supports</th><th>Status</th></tr>')
                wt.write('p','','Status as at {}'.format(actor.status_date if hasattr(actor,'status_date') else "N/A"))
                for depl in component_sets[component_set]:
                    wt.open('tr')
                    wt.writeNestedObjectLink('td',depl.htmlClass(),depl.component)
                    wt.write('td',depl.htmlClass(), depl.component.type)
                    wt.write('td',depl.htmlClass(), depl.locationDescription())
                    wt.open('td',depl.htmlClass())
                    for ark in sorted(depl.primary_requirements.keys()):
                        ar = depl.primary_requirements[ark]
                        wt.writeObjectLink(ar,ar.uid)
                    for ark in sorted(depl.secondary_requirements.keys()):
                        ar = depl.secondary_requirements[ark]
                        wt.writeObjectLink(ar,'('+ar.uid+')')
                    wt.close()
                    wt.write('td',depl.htmlClass(), depl.verboseStatus())
                    wt.close()
                wt.close()

    if(hasattr(actor,'unexpected_packages') and len(actor.unexpected_packages)>0):
        wt.write('h2','','Unexpected Software Components')
        wt.write('p','','As at {}'.format(actor.status_date))
        wt.open('table')
        wt.writeText('<tr><th>Package</th><th>Description</th>')
        for pkg in actor.unexpected_packages:
            wt.open('tr')
            wt.write('td','class="fault"',pkg[0])
            wt.write('td','class="fault"',pkg[1])
            wt.close()
        wt.close()

    if actor.type == 'host':
        reports = actor.getStatusReportList()
        if len(reports) > 0:
            att_hdr_list = reports[0].getAttributesAndHeaders()
            wt.write('h2','','Status Reports')
            wt.open('table')
            wt.open('tr')
            for att_hdr in att_hdr_list:
                wt.write('th','',att_hdr[1])
            wt.close()
            for report in reports:
                wt.open('tr')
                for att_hdr in att_hdr_list:
                    wt.write('td','',report.getFormattedAttribute(att_hdr[0]))
                wt.close()
            wt.close()


def makeCapabilityHtml(capability):
    """Creates an html file for the specified capability"""
    wt = BodyTagWriter(os.path.join(WEB_OUTPUT_DIR,capability.htmlName()),None, "Capability" + " : " + capability.name)

    wt.write('p', '', capability.description)

    wt.write('h2','','Basics')
    wt.writeText('<p><b>Health :</b> {}</p>'.format(capability.health))
    wt.writeAttributePara(capability, 'Status', 'status')
    wt.writeAttributePara(capability, 'Notes', 'notes')

    #Build summary requirements table
    wt.write('h2','','System Requirements Summary')

    wt.open('table')
    wt.writeSystemRequirementHeader()
    for sr in capability.requirement_list:
        wt.writeSystemRequirementRow(sr)
    wt.close()

    #Build partitioning table
    wt.write('h2','','Partitioning')
    wt.open('table')
    wt.writeText('<tr><th>Type</th><th>Actor</th><th>Responsibility</th><th>Rationale</th></tr>')
    for rsp in capability.responsibility_list:
        wt.open('tr')
        wt.write('td','', rsp.actor.type)
        wt.writeNestedObjectLink('td','',rsp.actor)
        wt.write('td','', rsp.description)
        wt.write('td','', rsp.rationale if hasattr(rsp,'rationale') else "&nbsp;")
        wt.close()
    wt.close()

    
    #Build detailed tables for each system requirement
    wt.write('h2','','System Requirements Breakdown')

    for sr in capability.requirement_list:

        users = sorted(sr.userSets(), key=lambda act: act.name)
        hosts = sorted(sr.hosts(), key=lambda act: act.name)

        #Summary information
        wt.writeText('<h3>&nbsp;</h3>')
        wt.writeText('<h3><a name="{}"></a>{} - {}</h3>'.format(sr.uid,sr.uid,sr.text))
        wt.writeAttributePara(sr, 'Importance', 'importance_text')
        wt.writeAttributePara(sr.verification, 'Verification', 'description')
        wt.writeAttributePara(sr, 'Decomposition', 'decomposition')
        wt.writeAttributePara(sr, None, 'notes')

        #Table of automatic checks
        if len(sr.automatic_checks) > 0:
            wt.open('table')
            wt.writeAutomaticCheckHeader()
            for chk in sr.automatic_checks:
                wt.writeAutomaticCheckRow(chk)
            wt.close()

        #Table of manual checks
        if len(sr.manual_checks) > 0:
            wt.open('table')
            wt.writeText('<tr><th>Manual Check</th><th>User</th><th>Frequency</th></tr>')
            for chk in sr.manual_checks:
                wt.open('tr')
                wt.write('td', chk.htmlClass(), chk.name)
                wt.write('td', chk.htmlClass(), chk.user)
                wt.write('td', chk.htmlClass(), chk.frequency)
                wt.close()
            wt.close()

        #Table of host requirements
        wt.open('table')
        wt.open('tr')
        wt.writeText('<th>UID</th><th>Owner</th><th>Text</th><th>Status</th>')
        for act in users + hosts:
            wt.writeNestedObjectLink('th','',act)
        wt.close()
        for ar in sr.actor_requirement_list:
            wt.open('tr')
            wt.write('td',ar.htmlClass(), ar.uid)
            wt.writeNestedObjectLink('td',ar.htmlClass(),ar.actor)
            wt.write('td',ar.htmlClass(), ar.text)
            wt.write('td',ar.htmlClass(),ar.status)
            for act in users:
                if act is ar.actor: wt.write('td','class="unmonitored"','&nbsp;')
                else:               wt.write('td','class="null"')
            for act in hosts:
                if act is ar.actor or (ar.actor.isGroup() and act in ar.actor.members.values()):
                    wt.open('td','class="container"')
                    wt.open('table','class="subtable"')
                    applicable_deployments = [depl for depl in act.expected_deployments.values() 
                                              if ar in depl.primary_requirements.values()]
                    for depl in sorted(applicable_deployments, key=lambda depl: depl.component.name):
                        wt.writeText('<tr><td class="{}"><a href="{}">{}</a></td></tr>'.format(
                                     depl.functionalHealth(), depl.component.htmlName(), depl.component.name))
                    wt.close(2)
                else:
                    wt.write('td','class="null"')
            wt.close()
        wt.close()


  
def makeComponentHtml(component,english):
    """Creates an html file for the specified component"""
    wt = BodyTagWriter(os.path.join(WEB_OUTPUT_DIR,component.htmlName()),None, english + " : " + component.name) 

    #Basic attributes
    wt.write('h2','','Basics')
    wt.writeAttributePara(component, 'Repository Distribution', 'repo_distribution')
    wt.writeAttributePara(component, 'Repository Distribution', 'repo_component')
    wt.writeAttributePara(component, 'Directory', 'directory')

    if hasattr(component,'package'):
        if len(component.package)==1:
            wt.writeText('<p><b>Repository Package :</b> {}</p>'.format(component.package[0]))
        else:
            wt.writeText('<p><b>Repository Package :</b> Multiple (see below for details)</p>')
    wt.writeAttributePara(component, 'Category', 'category')
    wt.writeAttributePara(component, 'Vendor', 'vendor')
    wt.writeAttributePara(component, 'Vendor URL', 'vendor_url')
    wt.writeAttributePara(component, 'Installation Type', 'installation_type')
    wt.writeAttributePara(component, 'Install Location', 'install_location')
    wt.writeAttributePara(component, 'Installation File', 'installation_file')
    if hasattr(component,'language'):
        wt.writeText('<p><b>Language : </b>{}</p>'.format(component.language.name))
    #Ensure health and therefore status are up to date by writing health first
    wt.writeText('<p><b>Health :</b> {}</p>'.format(component.health))
    wt.writeAttributePara(component, 'Status', 'status')
    if hasattr(component,'cm_location'):
        wt.write('h2','','Configuration Management')
        wt.writeAttributePara(component, 'CM Repository', 'cm_repository')
        wt.writeAttributePara(component, 'CM Location', 'cm_location')
        wt.writeAttributePara(component, 'CM File Name', 'cm_filename')
    if hasattr(component,'notes'):
        wt.write('h2','','Notes')
        wt.write('p','',component.notes)

    #Table of all (expected) deployments
    wt.write('h2','','Deployments')
    if len(component.deployments) == 0:
        wt.write('p','','No documented deployments to a host')
    else:
        has_packages = (hasattr(component,'package') and len(component.package)>1)
        host_names = sorted(component.deployments.keys())
        wt.open('table')
        wt.open('tr')
        wt.write('th','colspan = "{}"'.format(2 if has_packages else 1),'Target')
        for host_name in host_names: 
            wt.writeNestedObjectLink('th','',component.deployments[host_name].host)
        wt.close()
        wt.open('tr')
        wt.write('th','colspan = "{}"'.format(2 if has_packages else 1),'Supported Requirements')
        for host_name in host_names: 
            depl = component.deployments[host_name]
            wt.open('td',component.deployments[host_name].htmlClass())
            for ark in sorted(depl.primary_requirements.keys()):
                ar = depl.primary_requirements[ark]
                wt.writeObjectLink(ar.actor,ar.uid)
            for ark in sorted(depl.secondary_requirements.keys()):
                ar = depl.secondary_requirements[ark]
                wt.writeObjectLink(ar.actor,"("+ar.uid+")")
            wt.close()
        wt.close()
        wt.open('tr')
        wt.open('tr')
        wt.write('th','colspan = "{}"'.format(2 if has_packages else 1),'Deployment Location')
        for host_name in host_names: 
            wt.write('td',component.deployments[host_name].htmlClass(),component.deployments[host_name].locationDescription())
        wt.close()
        wt.write('th','colspan = "{}"'.format(2 if has_packages else 1),'Deployment State')
        for host_name in host_names: 
            wt.write('td',component.deployments[host_name].htmlClass(),component.deployments[host_name].status)
        wt.close()
        wt.open('tr')
        wt.write('th','colspan = "{}"'.format(2 if has_packages else 1),'Functional State')
        for host_name in host_names: 
            depl = component.deployments[host_name]
            wt.write('td','class="{}"'.format(depl.functionalHealth()),depl.functionalStatus())
        wt.close()

        if has_packages:
            for pkg in component.package:
                wt.open('tr')
                if pkg is component.package[0]: 
                    wt.write('th','rowspan = "{}"'.format(len(component.package)),'Packages')
                wt.write('td','',pkg)
                for host_name in host_names:
                    if not hasattr(component.deployments[host_name],'installed_packages'):
                        wt.write('td','class="unknown"','Unknown')
                    elif pkg in component.deployments[host_name].installed_packages:
                        wt.write('td','class="good"','Installed')
                    else:
                        wt.write('td','class="degd"','Missing')
                wt.close()
        wt.close()
        

    #Table of all dependencies
    wt.write('h2','','Dependants')
    if len(component.dependers) == 0:
        wt.write('p','','No other software components depend on this')
    else:
        wt.open('table')
        wt.writeText('<tr><th>Name</th><th>Type</th></tr>')
        for dep_name in sorted(component.dependers.keys()):
            dep = component.dependers[dep_name]
            wt.open('tr')
            wt.writeNestedObjectLink('td',dep.htmlClass(),dep)
            wt.write('td',dep.htmlClass(), dep.type)
            wt.close()
        wt.close()
        
    #Table of all dependencies
    wt.write('h2','','Dependencies')
    if len(component.dependencies) == 0:
        wt.write('p','','Does not depend on any other software components')
    else:
        wt.open('table')
        wt.writeText('<tr><th>Name</th><th>Type</th></tr>')
        for dep_name in sorted(component.dependencies.keys()):
            dep = component.dependencies[dep_name]
            wt.open('tr')
            wt.writeNestedObjectLink('td',dep.htmlClass(),dep)
            wt.write('td',dep.htmlClass(), dep.type)
            wt.close()
        wt.close()
        
    #Table of all relationships
    wt.write('h2','','Relationships')
    if len(component.relations) == 0:
        wt.write('p','','Is not related to any other software components')
    else:
        wt.open('table')
        wt.writeText('<tr><th>Name</th><th>Type</th></tr>')
        for rel_name in sorted(component.relations.keys()):
            rel = component.relations[rel_name]
            wt.open('tr')
            wt.writeNestedObjectLink('td',rel.htmlClass(),rel)
            wt.write('td',rel.htmlClass(), rel.type)
            wt.close()
        wt.close()

    #For CM files actually bring in the file itself
    if isinstance(component,sitemgt.CmComponent):
        svn_name = component.url()
        
        wt.write('h2','','File Contents')
        wt.open('pre')
        try:
            file_data = subprocess.check_output('svn {} cat "{}" 2>&1'.format(auth.subversionParams(),svn_name),shell=True).decode('utf-8') 
            wt.writeText(file_data.replace('<','&lt;').replace('>','&gt;'))
        except Exception:
            wt.writeText("Could not read contents for {}".format(svn_name))
        wt.close()                 

        wt.write('h2','','File Log')
        wt.open('pre')
        try:
            log_data = subprocess.check_output('svn {} log "{}" 2>&1'.format(auth.subversionParams(),svn_name),shell=True).decode('utf-8') 
            wt.writeText(log_data.replace('<','&lt;').replace('>','&gt;'))
        except Exception:
            wt.writeText("Could not read log for {}".format(svn_name))
        wt.close()                 

             

def makeAutomaticCheckHtml(check, english):
    """Creates an html file for the specified component"""
    output_filename = os.path.join(WEB_OUTPUT_DIR, check.htmlName()) 
    wt = BodyTagWriter(output_filename, None, english + " : " + check.name) 

    wt.write('h2','','Supported Requirements')
    wt.open('table')
    wt.writeSystemRequirementHeader()
    for sr in sorted(check.requirements.keys()):
        wt.writeSystemRequirementRow(check.requirements[sr])
    wt.close()

    wt.write('h2','','Execution History')
    wt.open('table')
    wt.writeCheckOutcomeHeader()
    for outcome in reversed(check.outcomes) if check.outcomes else ():
        wt.writeCheckOutcomeRow(outcome)
    wt.close()




if __name__ == '__main__':
    
    #First wipe out the contents of the output directory
    for f in os.listdir(WEB_OUTPUT_DIR):
        os.unlink(os.path.join(WEB_OUTPUT_DIR, f))
    
    # Gather authorization for subversion
    if not auth.readFromFile():
        print("ERROR: Could not find a valid authorization in {}".format(auth.filename))
        sys.exit(1)
    
    #Parse the data
    sd = sitemgt.SiteDescription(SITE_XML_FILE)
    sd.loadDeploymentStatusFromXmlFile()

    #Build all the list htmls for the index pane
    makeListHtml([('User Groups',sd.user_groups),('Users',sd.users)], 'Users', 'Users.html')
    makeListHtml([('Host Groups',sd.host_groups),('Hosts',sd.hosts)], 'Hosts and Host Groups', 'Hosts.html')
    makeListHtml([('Capabilities',sd.capabilities)], 'Capabilities', 'Capabilities.html')
    makeListHtml([('Applications',sd.applications)], 'Applications', 'Applications.html')
    makeListHtml([('Config Files',sd.config_files),('Other Files',sd.other_files)], 'Files', 'Files.html')
    makeListHtml([('Scripts',sd.scripts)], 'Scripts', 'Scripts.html')
    makeListHtml([('Checks',sd.automatic_checks)], 'Automatic Checks', 'Checks.html')

    #Build all the summary htmls for the data pane
    makeSummariesHtml('All Users and User Groups',[('User Groups',sd.user_groups,[],[]),('Users',sd.users,['account_type'],['Type'])], 'Users.html')
    makeSummariesHtml('All Hosts and Host Groups',[('Host Groups',sd.host_groups,['description'],['Description']),('Hosts',sd.hosts,['ip_address','os','status','status_date'],['IP Address','OS','Status','Status Date'])], 'Hosts.html')
    makeSummariesHtml('All Applications',[('',sd.applications,['type'],['Type'])], 'Applications.html')
    makeSummariesHtml('All Files',[('Config Files',sd.config_files,['status'],['Status']),('Other Files',sd.other_files,['category','status'],['Category','Status'])], 'Files.html')
    makeSummariesHtml('All Scripts', [('',sd.scripts,['language','status'],['Language','Status'])], 'Scripts.html')
    makeCapabilitySummariesHtml(sd.capabilities)
    makeSummariesHtml('All Automatic Checks', [('',sd.automatic_checks,['last_run','status'],['Last Run','Status'])], 'Checks.html')

    for actor in sd.users.values():
        makeActorHtml(actor, "User", False)
    for actor in sd.user_groups.values():
        makeActorHtml(actor, "User Group", True)
    for actor in sd.hosts.values():
        makeActorHtml(actor, "Host", False)
    for actor in sd.host_groups.values():
        makeActorHtml(actor, "Host Group", True)

    for capability in sd.capabilities:
        makeCapabilityHtml(capability)

    for component in sd.applications.values():
        makeComponentHtml(component,"Application")
    for component in sd.config_files.values():
        makeComponentHtml(component,"Config File")
    for component in sd.other_files.values():
        makeComponentHtml(component,"Other File")
    for component in sd.scripts.values():
        makeComponentHtml(component,"Script")

    for check in sd.automatic_checks.values():
        makeAutomaticCheckHtml(check,"Check")
    
    
    
