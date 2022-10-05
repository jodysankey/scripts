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
# AppliesTo: linux
# AppliesTo: server
# RemoveExtension: True
#========================================================
# Possible Improvements:
# * Colorize output of Python
# * Colorize output of bash comments
# * Selectively pull in deployed files where available
#   and where permissions are appropriate e.g. scripts
#========================================================

import argparse
from datetime import datetime
import os
import subprocess
from subprocess import CalledProcessError, DEVNULL
import sys

import git_validation
import sitemgt
from sitemgt.paths import CM_WORKING_DIR, CM_UPSTREAM_DIR, SITE_XML_FILE
import tagwriter

GIT_LOG_COMMAND = ('git', 'log', '--pretty=format:%h - %s (%ci)', '--abbrev-commit')
OUTPUT_ROOT = None

class BodyTagWriter(tagwriter.TagWriter):
    """Extends simple tag writer to open and close a standard data html."""

    def __init__(self, filename, class_name, parent_title):
        super().__init__(filename)
        self.write_orphan('!DOCTYPE', 'html')
        self.open('html')
        self.write_orphan('link', 'rel="stylesheet" href="../static/style.css" typename="text/css"')
        self.write_orphan('meta', 'http-equiv="Content-Type" content="text/html;charset=utf-8"')

        attr = ""
        if class_name is not None:
            attr += ' class="{}"'.format(class_name)
        if parent_title is not None:
            json = "{{'title': '{}', 'date': '{}'}}".format(
                parent_title, datetime.today().strftime("Page generated at: %Y-%m-%d %H:%M"))
            attr += ' onload="parent.title.postMessage(JSON.stringify({}), \'*\');"'.format(json)
        self.open('body', attr)

    def __del__(self):
        if self.depth() < 2:
            print("Tried to close too many tags in: " + self.filename)
        self.close()
        self.close()
        super().__del__()

    def write_attribute_para(self, obj, english_name, attr_name):
        if hasattr(obj, attr_name):
            if english_name is None:
                self.write_text('<p>{}</p>'.format(getattr(obj, attr_name)))
            else:
                self.write_text('<p><b>{} :</b> {}</p>'.format(
                    english_name, getattr(obj, attr_name)))

    def write_link(self, text, destination, target_frame=None):
        if target_frame is None:
            self.write('a', 'href="{}"'.format(destination), text)
        else:
            self.write('a', 'href="{}" target="{}"'.format(destination, target_frame), text)

    def write_object_link(self, site_object, text=None, target_frame=None):
        if text is None:
            text = site_object.name
        self.write_link(text=text, destination=site_object.htmlName(), target_frame=target_frame)

    def write_nested_object_link(self, tag, attributes, site_object, target_frame=None):
        self.open(tag, attributes)
        self.write_object_link(site_object, None, target_frame)
        self.close()

    def write_system_requirement_header(self):
        self.write_text('<tr><th>UID</th><th>Text</th><th>Importance</th>'
                        '<th>Verification</th><th>Status</th></tr>')
    def write_system_requirement_row(self, system_requirement, generate_row_tag=True):
        if generate_row_tag:
            self.open('tr')
        cls = system_requirement.htmlClass()
        self.write_nested_object_link('td', cls, system_requirement)
        self.write('td', cls, system_requirement.text)
        self.write('td', cls, system_requirement.importance_text)
        self.write('td', cls, system_requirement.verification.description)
        self.write('td', cls, system_requirement.status)
        if generate_row_tag:
            self.close() #TR

    def write_automatic_check_header(self):
        self.write_text('<tr><th>Automatic Check</th><th>Last Run</th>'
                        '<th>Outcome</th><th>Description</th></tr>')
    def write_automatic_check_row(self, automatic_check, generate_row_tag=True):
        if generate_row_tag:
            self.open('tr')
        cls = automatic_check.htmlClass()
        self.write_nested_object_link('td', cls, automatic_check)
        if automatic_check.lastOutcome():
            self.write_check_outcome_row(automatic_check.lastOutcome(), cls, False)
        else:
            self.write('td', cls, "N/A")
            self.write('td', cls, "N/A")
            self.write('td', cls, automatic_check.result_error
                       if hasattr(automatic_check, 'result_error') else 'UNKNOWN')
        if generate_row_tag:
            self.close() #TR

    def write_check_outcome_header(self):
        self.write_text('<tr><th>Run</th><th>Outcome</th><th>Description</th></tr>')
    def write_check_outcome_row(self, outcome, html_class=None, generate_row_tag=True):
        if generate_row_tag:
            self.open('tr')
        if html_class is None:
            html_class = ' class="{}"'.format('good' if outcome.success else 'fail')
        self.write('td', html_class, outcome.timestamp)
        self.write('td', html_class, outcome.outcome())
        self.write('td', html_class, outcome.description)
        if generate_row_tag:
            self.close() #TR

    # TODO: Consider adding more of these object specific write functions to simplify the page
    # generators


def make_list_html(heading_iterable_list, object_description, output_base):
    """Creates an html file to list the specified elements."""
    list_filename = os.path.join(OUTPUT_ROOT, "list_" + output_base)
    writer = BodyTagWriter(list_filename, 'list', parent_title=None)

    writer.open('p', '')
    writer.write_link(text='All ' + object_description, destination='all_' + output_base,
                      target_frame='data')
    writer.close()
    for (heading, iterable) in heading_iterable_list:
        writer.write('h3', '', heading)
        if isinstance(iterable, dict):
            for k in sorted(iterable.keys()):
                writer.write_nested_object_link('p', '', iterable[k], target_frame='data')
        else:
            for value in iterable:
                writer.write_nested_object_link('p', '', value, target_frame='data')


def make_summaries_html(master_hdg, hdg_dict_att_titles_pfx, output_base):
    """Creates an html file to summarize state of the specified elements."""
    summary_filename = os.path.join(OUTPUT_ROOT, "all_" + output_base)
    writer = BodyTagWriter(summary_filename, None, master_hdg)

    for (heading, dic, attributes, titles) in hdg_dict_att_titles_pfx:
        writer.write('h3', '', heading)
        writer.open('table')
        writer.open('tr')
        writer.write('th', '', 'Name')
        for title in titles:
            writer.write('th', '', title)
        writer.write('th', '', 'Requirements')
        writer.close()  #TR
        for ob_name in sorted(dic.keys()):
            ob = dic[ob_name]
            writer.open('tr')
            writer.write_nested_object_link('td', ob.htmlClass(), ob)
            for att in attributes:
                writer.write('td', ob.htmlClass(),
                             getattr(ob, att) if hasattr(ob, att) else '&nbsp;')
            writer.open('td', ob.htmlClass())
            if hasattr(ob, 'requirements') and ob.requirements:
                for uid in sorted(ob.requirements.keys()):
                    writer.write_object_link(ob.requirements[uid])
            else:
                writer.write_text("&nbsp;")
            writer.close()  #TD
            writer.close()  #TR
        writer.close()      #Table


def make_capability_summaries_html(capabilities):
    """Creates an html file to summarizes all capabilities. Two layer table requires unique code"""
    summary_filename = os.path.join(OUTPUT_ROOT, "all_Capabilities.html")
    writer = BodyTagWriter(summary_filename, None, "All Capabilities")

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

    writer.write("p", "", ("Next System requirement <b>S{:03}</b>, Host requirement <b>H{:03}</b>,"
                           + " User requirement <b>U{:03}</b>").format(
                               max_sys + 1, max_host + 1, max_user + 1))
    writer.open('table')
    writer.write_text('<tr><th colspan="2">Capability</th>'
                      '<th colspan="5">System Requirement</th></tr>')
    writer.write_text('<tr><th>Title</th><th>Status</th><th>UID</th><th>Text</th>'
                      '<th>Importance</th><th>Verification</th><th>Status</th></tr>')

    # TODO: Move counts of each status into sitedescription
    status_to_classcount = {}

    for cap in capabilities:
        writer.open('tr')
        row_count = max(1, len(cap.requirement_list))
        writer.write_nested_object_link(
            'td', cap.htmlClass() + ' rowspan="{}"'.format(row_count), cap)
        writer.write('td', cap.htmlClass() + ' rowspan="{}"'.format(row_count), cap.status)
        if not cap.requirement_list:
            writer.write('td', 'hspan="5"', 'No system requirements')
            writer.close()
        else:
            for req in cap.requirement_list:
                if req is not cap.requirement_list[0]:
                    writer.open('tr')
                writer.write_system_requirement_row(req, generate_row_tag=False)
                writer.close() #Row
                if req.status not in status_to_classcount.keys():
                    status_to_classcount[req.status] = [req.htmlClass(), 1]
                else:
                    status_to_classcount[req.status][1] += 1
    writer.close() #Table

    writer.write('p', '', ' ')
    writer.open('table')
    writer.write_text('<tr><th>Status</th><th>Proportion</th></tr>')
    total = sum([v[1] for v in status_to_classcount.values()])
    for item in sorted(status_to_classcount.items(), key=lambda x: x[1][1], reverse=True):
        writer.open('tr')
        writer.write('td', item[1][0], item[0])
        writer.write('td', item[1][0], "{:.1f}%".format((item[1][1] / total) * 100.0))
        writer.close() #Row
    writer.close() #Table


def make_actor_html(actor, english, is_group):
    """Creates an html file for the specified actor"""
    writer = BodyTagWriter(os.path.join(OUTPUT_ROOT, actor.htmlName()), None,
                           english + " : " + actor.name)

    # Basic attributes
    writer.write('h2', '', 'Basics')
    if actor.type == 'host':
        writer.write_attribute_para(actor, 'IP Address', 'ip_address')
        writer.write_attribute_para(actor, 'Purpose', 'purpose')
        writer.write_attribute_para(actor, 'Operating System', 'os')
        writer.write_attribute_para(actor, 'Last Status', 'status_date')
    elif actor.type == 'user':
        writer.write_attribute_para(actor, 'Type', 'account_type')
        writer.write_attribute_para(actor, 'e-mail', 'email')
    else:
        writer.write_attribute_para(actor, 'Description', 'description')

    # Either members of a group, or groups of a member
    if is_group:
        writer.write('h2', '', 'Members')
        for k in sorted(actor.members.keys()):
            writer.write_nested_object_link('p', '', actor.members[k])
    else:
        writer.write('h2', '', 'Groups')
        if actor.groups:
            for k in sorted(actor.groups.keys()):
                writer.write_nested_object_link('p', '', actor.groups[k])
        else:
            writer.write('p', '', '{} is not a member of any groups'.format(actor.name))

    # Build responsibility table
    responsibilities = actor.responsibilities
    if not is_group:
        for group in actor.groups.values():
            responsibilities.update(group.responsibilities)
    if responsibilities:
        writer.write('h2', '', 'Responsibilities')
        writer.open('table')
        writer.write_text('<tr><th>Capability</th><th>Target</th>'
                          '<th>Description</th><th>Rationale</tr>')
        for rk in sorted(responsibilities.keys()):
            rsp = responsibilities[rk]
            writer.open('tr')
            writer.write_nested_object_link('td', '', rsp.capability)
            writer.write('td', '', rsp.actor.name)
            writer.write('td', '', rsp.description)
            writer.write('td', '', rsp.rationale if hasattr(rsp, 'rationale') else "&nbsp;")
            writer.close()
        writer.close()
# Build requirements tables
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
        writer.write('h2', '', 'Requirements')
        writer.open('table')
        writer.open('tr')
        writer.write_text('<th>UID</th><th>Site Level Status</th>'
                          '<th>Target</th><th>Text</th><th>Supports</th>')
        for host_name in sorted(hosts.keys()):
            writer.write('th', '', 'Software' if len(hosts) == 1 else host_name)
        writer.close()

        for ark in sorted(requirements.keys()):
            ar = requirements[ark]
            writer.open('tr')
            writer.write('a', 'name="{}"'.format(ar.uid))

            normal_class = ar.htmlClass() if actor is ar.actor else 'class="unknown"'
            # Only hyperlink to the real owner if its not us
            if actor is ar.actor:
                writer.write('td', normal_class, ark)
            else:
                writer.open('td', normal_class)
                writer.write_object_link(ar, ark)
                writer.close()
            writer.write('td', normal_class, ar.status)
            writer.write('td', normal_class, ar.actor.name)
            writer.write('td', normal_class, ar.text)
            writer.open('td', normal_class)
            for srk in sorted(ar.system_requirements.keys()):
                sr = ar.system_requirements[srk]
                writer.write_object_link(sr, sr.uid)
            writer.close()
            for hn in sorted(hosts.keys()):
                h = hosts[hn]
                writer.open('td', 'class="container"')
                writer.open('table', 'class="subtable"')
                for depl in [d for d in h.expected_deployments.values()
                             if ar in d.primary_requirements.values()]:
                    writer.write_text('<tr><td class="{}"><a href="{}">{}</a></td></tr>'.format(
                        depl.functionalHealth(), depl.component.htmlName(), depl.component.name))
                writer.close(2)
            writer.close()
        writer.close()

    #Report whether any upgrades are necessary
    if hasattr(actor, 'upgradable_packages') and actor.upgradable_packages:
        writer.write('h2', '', '{} Software Packages Require Upgrade!'.format(
            len(actor.upgradable_packages)))
        writer.write('p', '', 'As at {}'.format(actor.status_date))

    if hasattr(actor, 'expected_deployments'):
        #Split expected components by type (i.e. Application/File/Script)
        component_sets = {}
        component_sets['Applications'] = sorted(
            [d for d in actor.expected_deployments.values() if
             d.component.type.endswith('application')], key=lambda depl: depl.component.name)
        component_sets['Scripts'] = sorted(
            [d for d in actor.expected_deployments.values() if
             d.component.type == 'script'], key=lambda depl: depl.locationDescription())
        component_sets['Files'] = sorted(
            [d for d in actor.expected_deployments.values() if
             d.component.type.endswith('file')], key=lambda depl: depl.locationDescription())

        for component_set in sorted(component_sets.keys()):
            writer.write('h2', '', 'Expected ' + component_set)
            if not component_sets[component_set]:
                writer.write('p', '', 'No documented ' + component_set.lower())
            else:
                writer.open('table')
                writer.write_text('<tr><th>Name</th><th>Type</th><th>Location</th>'
                                  '<th>Supports</th><th>Status</th></tr>')
                writer.write('p', '', 'Status as at {}'.format(
                    actor.status_date if hasattr(actor, 'status_date') else "N/A"))
                for depl in component_sets[component_set]:
                    writer.open('tr')
                    writer.write_nested_object_link('td', depl.htmlClass(), depl.component)
                    writer.write('td', depl.htmlClass(), depl.component.type)
                    writer.write('td', depl.htmlClass(), depl.locationDescription())
                    writer.open('td', depl.htmlClass())
                    for ark in sorted(depl.primary_requirements.keys()):
                        ar = depl.primary_requirements[ark]
                        writer.write_object_link(ar, ar.uid)
                    for ark in sorted(depl.secondary_requirements.keys()):
                        ar = depl.secondary_requirements[ark]
                        writer.write_object_link(ar, '('+ar.uid+')')
                    writer.close()
                    writer.write('td', depl.htmlClass(), depl.verboseStatus())
                    writer.close()
                writer.close()

    if hasattr(actor, 'unexpected_packages') and actor.unexpected_packages:
        writer.write('h2', '', 'Unexpected Software Components')
        writer.write('p', '', 'As at {}'.format(actor.status_date))
        writer.open('table')
        writer.write_text('<tr><th>Package</th><th>Description</th>')
        for pkg in actor.unexpected_packages:
            writer.open('tr')
            writer.write('td', 'class="fault"', pkg[0])
            writer.write('td', 'class="fault"', pkg[1])
            writer.close()
        writer.close()

    if actor.type == 'host':
        reports = actor.getStatusReportList()
        if reports:
            att_hdr_list = reports[0].getAttributesAndHeaders()
            writer.write('h2', '', 'Status Reports')
            writer.open('table')
            writer.open('tr')
            for att_hdr in att_hdr_list:
                writer.write('th', '', att_hdr[1])
            writer.close()
            for report in reports:
                writer.open('tr')
                for att_hdr in att_hdr_list:
                    writer.write('td', '', report.getFormattedAttribute(att_hdr[0]))
                writer.close()
            writer.close()


def make_capability_html(capability):
    """Creates an html file for the specified capability"""
    writer = BodyTagWriter(os.path.join(OUTPUT_ROOT, capability.htmlName()),
                           None, "Capability" + " : " + capability.name)

    writer.write('p', '', capability.description)

    writer.write('h2', '', 'Basics')
    writer.write_text('<p><b>Health :</b> {}</p>'.format(capability.health))
    writer.write_attribute_para(capability, 'Status', 'status')
    writer.write_attribute_para(capability, 'Notes', 'notes')

    # Build summary requirements table
    writer.write('h2', '', 'System Requirements Summary')

    writer.open('table')
    writer.write_system_requirement_header()
    for sr in capability.requirement_list:
        writer.write_system_requirement_row(sr)
    writer.close()

    # Build partitioning table
    writer.write('h2', '', 'Partitioning')
    writer.open('table')
    writer.write_text('<tr><th>Type</th><th>Actor</th>'
                      '<th>Responsibility</th><th>Rationale</th></tr>')
    for rsp in capability.responsibility_list:
        writer.open('tr')
        writer.write('td', '', rsp.actor.type)
        writer.write_nested_object_link('td', '', rsp.actor)
        writer.write('td', '', rsp.description)
        writer.write('td', '', rsp.rationale if hasattr(rsp, 'rationale') else "&nbsp;")
        writer.close()
    writer.close()

    # Build detailed tables for each system requirement
    writer.write('h2', '', 'System Requirements Breakdown')
    for sr in capability.requirement_list:
        users = sorted(sr.userSets(), key=lambda act: act.name)
        hosts = sorted(sr.hosts(), key=lambda act: act.name)

        # Summary information
        writer.write_text('<h3>&nbsp;</h3>')
        writer.write_text('<h3><a name="{}"></a>{} - {}</h3>'.format(sr.uid, sr.uid, sr.text))
        writer.write_attribute_para(sr, 'Importance', 'importance_text')
        writer.write_attribute_para(sr.verification, 'Verification', 'description')
        writer.write_attribute_para(sr, 'Decomposition', 'decomposition')
        writer.write_attribute_para(sr, None, 'notes')

        # Table of automatic checks
        if sr.automatic_checks:
            writer.open('table')
            writer.write_automatic_check_header()
            for chk in sr.automatic_checks:
                writer.write_automatic_check_row(chk)
            writer.close()

        # Table of manual checks
        if sr.manual_checks:
            writer.open('table')
            writer.write_text('<tr><th>Manual Check</th><th>User</th><th>Frequency</th></tr>')
            for chk in sr.manual_checks:
                writer.open('tr')
                writer.write('td', chk.htmlClass(), chk.name)
                writer.write('td', chk.htmlClass(), chk.user)
                writer.write('td', chk.htmlClass(), chk.frequency)
                writer.close()
            writer.close()

        # Table of host requirements
        writer.open('table')
        writer.open('tr')
        writer.write_text('<th>UID</th><th>Owner</th><th>Text</th><th>Status</th>')
        for act in users + hosts:
            writer.write_nested_object_link('th', '', act)
        writer.close()
        for ar in sr.actor_requirement_list:
            writer.open('tr')
            writer.write('td', ar.htmlClass(), ar.uid)
            writer.write_nested_object_link('td', ar.htmlClass(), ar.actor)
            writer.write('td', ar.htmlClass(), ar.text)
            writer.write('td', ar.htmlClass(), ar.status)
            for act in users:
                if act is ar.actor:
                    writer.write('td', 'class="unmonitored"', '&nbsp;')
                else:
                    writer.write('td', 'class="null"')
            for act in hosts:
                if act is ar.actor or (ar.actor.isGroup() and act in ar.actor.members.values()):
                    writer.open('td', 'class="container"')
                    writer.open('table', 'class="subtable"')
                    applicable_deployments = [depl for depl in act.expected_deployments.values()
                                              if ar in depl.primary_requirements.values()]
                    for depl in sorted(applicable_deployments,
                                       key=lambda depl: depl.component.name):
                        writer.write_text('<tr><td class="{}"><a href="{}">{}</a></td></tr>'.format(
                            depl.functionalHealth(), depl.component.htmlName(),
                            depl.component.name))
                    writer.close(2)
                else:
                    writer.write('td', 'class="null"')
            writer.close()
        writer.close()


def make_component_html(component, english):
    """Creates an html file for the specified component"""
    writer = BodyTagWriter(os.path.join(OUTPUT_ROOT, component.htmlName()),
                           None, english + " : " + component.name)

    # Basic attributes
    writer.write('h2', '', 'Basics')
    writer.write_attribute_para(component, 'Repository Distribution', 'repo_distribution')
    writer.write_attribute_para(component, 'Repository Distribution', 'repo_component')
    writer.write_attribute_para(component, 'Directory', 'directory')

    if hasattr(component, 'package'):
        if len(component.package) == 1:
            writer.write_text('<p><b>Repository Package :</b> {}</p>'.format(component.package[0]))
        else:
            writer.write_text('<p><b>Repository Package :</b> Multiple (see below for details)</p>')
    writer.write_attribute_para(component, 'Category', 'category')
    writer.write_attribute_para(component, 'Vendor', 'vendor')
    writer.write_attribute_para(component, 'Vendor URL', 'vendor_url')
    writer.write_attribute_para(component, 'Installation Type', 'installation_type')
    writer.write_attribute_para(component, 'Install Location', 'install_location')
    writer.write_attribute_para(component, 'Installation File', 'installation_file')
    if hasattr(component, 'language'):
        writer.write_text('<p><b>Language : </b>{}</p>'.format(component.language.name))
    # Ensure health and therefore status are up to date by writing health first
    writer.write_text('<p><b>Health :</b> {}</p>'.format(component.health))
    writer.write_attribute_para(component, 'Status', 'status')
    if hasattr(component, 'cm_location'):
        writer.write('h2', '', 'Configuration Management')
        writer.write_attribute_para(component, 'CM Repository', 'cm_repository')
        writer.write_attribute_para(component, 'CM Location', 'cm_location')
        writer.write_attribute_para(component, 'CM File Name', 'cm_filename')
    if hasattr(component, 'notes'):
        writer.write('h2', '', 'Notes')
        writer.write('p', '', component.notes)

    # Table of all (expected) deployments
    writer.write('h2', '', 'Deployments')
    if not component.deployments:
        writer.write('p', '', 'No documented deployments to a host')
    else:
        has_packages = hasattr(component, 'package') and component.package
        host_names = sorted(component.deployments.keys())
        writer.open('table')
        writer.open('tr')
        writer.write('th', 'colspan = "{}"'.format(2 if has_packages else 1), 'Target')
        for host_name in host_names:
            writer.write_nested_object_link('th', '', component.deployments[host_name].host)
        writer.close()
        writer.open('tr')
        writer.write('th', 'colspan = "{}"'.format(2 if has_packages else 1),
                     'Supported Requirements')
        for host_name in host_names:
            depl = component.deployments[host_name]
            writer.open('td', component.deployments[host_name].htmlClass())
            for ark in sorted(depl.primary_requirements.keys()):
                ar = depl.primary_requirements[ark]
                writer.write_object_link(ar.actor, ar.uid)
            for ark in sorted(depl.secondary_requirements.keys()):
                ar = depl.secondary_requirements[ark]
                writer.write_object_link(ar.actor, "(" + ar.uid + ")")
            writer.close()
        writer.close()
        writer.open('tr')
        writer.open('tr')
        writer.write('th', 'colspan = "{}"'.format(2 if has_packages else 1), 'Deployment Location')
        for host_name in host_names:
            writer.write('td', component.deployments[host_name].htmlClass(),
                         component.deployments[host_name].locationDescription())
        writer.close()
        writer.write('th', 'colspan = "{}"'.format(2 if has_packages else 1), 'Deployment State')
        for host_name in host_names:
            writer.write('td', component.deployments[host_name].htmlClass(),
                         component.deployments[host_name].status)
        writer.close()
        writer.open('tr')
        writer.write('th', 'colspan = "{}"'.format(2 if has_packages else 1), 'Functional State')
        for host_name in host_names:
            depl = component.deployments[host_name]
            writer.write('td', 'class="{}"'.format(
                depl.functionalHealth()), depl.functionalStatus())
        writer.close()

        if has_packages:
            for pkg in component.package:
                writer.open('tr')
                if pkg is component.package[0]:
                    writer.write('th', 'rowspan = "{}"'.format(len(component.package)), 'Packages')
                writer.write('td', '', pkg)
                for host_name in host_names:
                    if not hasattr(component.deployments[host_name], 'installed_packages'):
                        writer.write('td', 'class="unknown"', 'Unknown')
                    elif pkg in component.deployments[host_name].installed_packages:
                        writer.write('td', 'class="good"', 'Installed')
                    else:
                        writer.write('td', 'class="degd"', 'Missing')
                writer.close()
        writer.close()


    # Table of all dependants
    writer.write('h2', '', 'Dependants')
    if not component.dependers:
        writer.write('p', '', 'No other software components depend on this')
    else:
        writer.open('table')
        writer.write_text('<tr><th>Name</th><th>Type</th></tr>')
        for dep_name in sorted(component.dependers.keys()):
            dep = component.dependers[dep_name]
            writer.open('tr')
            writer.write_nested_object_link('td', dep.htmlClass(), dep)
            writer.write('td', dep.htmlClass(), dep.type)
            writer.close()
        writer.close()

    # Table of all dependencies
    writer.write('h2', '', 'Dependencies')
    if component.dependencies:
        writer.write('p', '', 'Does not depend on any other software components')
    else:
        writer.open('table')
        writer.write_text('<tr><th>Name</th><th>Type</th></tr>')
        for dep_name in sorted(component.dependencies.keys()):
            dep = component.dependencies[dep_name]
            writer.open('tr')
            writer.write_nested_object_link('td', dep.htmlClass(), dep)
            writer.write('td', dep.htmlClass(), dep.type)
            writer.close()
        writer.close()

    # Table of all relationships
    writer.write('h2', '', 'Relationships')
    if not component.relations:
        writer.write('p', '', 'Is not related to any other software components')
    else:
        writer.open('table')
        writer.write_text('<tr><th>Name</th><th>Type</th></tr>')
        for rel_name in sorted(component.relations.keys()):
            rel = component.relations[rel_name]
            writer.open('tr')
            writer.write_nested_object_link('td', rel.htmlClass(), rel)
            writer.write('td', rel.htmlClass(), rel.type)
            writer.close()
        writer.close()

    # For CM files actually bring in the file itself
    if isinstance(component, sitemgt.CmComponent):
        cm_path = os.path.join(CM_WORKING_DIR, component.cm_location, component.cm_filename)
        writer.write('h2', '', 'File Contents')
        writer.open('pre')
        try:
            file_data = open(cm_path, 'r').read()
            writer.write_text(file_data.replace('<', '&lt;').replace('>', '&gt;'))
        except OSError:
            writer.write_text("Could not read contents for {}".format(cm_path))
        writer.close()

        writer.write('h2', '', 'File Log')
        writer.open('pre')
        try:
            log_data = subprocess.check_output(
                list(GIT_LOG_COMMAND) + ['--', cm_path],
                cwd=CM_WORKING_DIR, stderr=DEVNULL).decode('utf-8')
            writer.write_text(log_data.replace('<', '&lt;').replace('>', '&gt;'))
        except CalledProcessError:
            writer.write_text("Could not read log for {}".format(cm_path))
        writer.close()


def make_automatic_check_html(check, english):
    """Creates an html file for the specified component"""
    output_filename = os.path.join(OUTPUT_ROOT, check.htmlName())
    writer = BodyTagWriter(output_filename, None, english + " : " + check.name)

    writer.write('h2', '', 'Supported Requirements')
    writer.open('table')
    writer.write_system_requirement_header()
    for sr in sorted(check.requirements.keys()):
        writer.write_system_requirement_row(check.requirements[sr])
    writer.close()

    writer.write('h2', '', 'Execution History')
    writer.open('table')
    writer.write_check_outcome_header()
    for outcome in reversed(check.outcomes) if check.outcomes else ():
        writer.write_check_outcome_row(outcome)
    writer.close()


def make_everything(args):
    """Creates the entire website, removing and existing files in the target directory."""
    global OUTPUT_ROOT

    # Check that the working site matches the master
    validation = git_validation.check_repo(CM_WORKING_DIR, CM_UPSTREAM_DIR)
    if not validation['is_valid']:
        print('ERROR: {} is not a valid git repo ({})'.format(CM_WORKING_DIR,
                                                              validation['problem']))
        sys.exit(1)
    if not validation['is_synchronized'] and not args.force:
        print('ERROR: {} is not in sync with upstream ({})'.format(CM_WORKING_DIR,
                                                                   validation['problem']))
        print('       run with --force to generate output anyway')
        sys.exit(1)
    OUTPUT_ROOT = args.destination
    if not os.path.isdir(OUTPUT_ROOT):
        print('ERROR: {} is not a directory'.format(OUTPUT_ROOT))
        sys.exit(1)
    if not os.path.exists(os.path.join(os.path.dirname(OUTPUT_ROOT), 'home.html')):
        print("ERROR: {} doesn't have home.html in its parent".format(OUTPUT_ROOT))
        sys.exit(1)

    for file in os.listdir(OUTPUT_ROOT):
        os.unlink(os.path.join(OUTPUT_ROOT, file))

    # Parse the data
    sd = sitemgt.SiteDescription(SITE_XML_FILE)
    sd.loadDeploymentStatusFromXmlFile()

    #Build all the list htmls for the index pane
    make_list_html([('User Groups', sd.user_groups), ('Users', sd.users)], 'Users', 'Users.html')
    make_list_html([('Host Groups', sd.host_groups), ('Hosts', sd.hosts)],
                   'Hosts and Host Groups', 'Hosts.html')
    make_list_html([('Capabilities', sd.capabilities)], 'Capabilities', 'Capabilities.html')
    make_list_html([('Applications', sd.applications)], 'Applications', 'Applications.html')
    make_list_html([('Config Files', sd.config_files), ('Other Files', sd.other_files)],
                   'Files', 'Files.html')
    make_list_html([('Scripts', sd.scripts)], 'Scripts', 'Scripts.html')
    make_list_html([('Checks', sd.automatic_checks)], 'Automatic Checks', 'Checks.html')

    #Build all the summary htmls for the data pane
    make_summaries_html('All Users and User Groups', [
        ('User Groups', sd.user_groups, [], []),
        ('Users', sd.users, ['account_type'], ['Type'])], 'Users.html')
    make_summaries_html('All Hosts and Host Groups', [
        ('Host Groups', sd.host_groups, ['description'], ['Description']),
        ('Hosts', sd.hosts,
         ['ip_address', 'os', 'status', 'status_date'],
         ['IP Address', 'OS', 'Status', 'Status Date'])], 'Hosts.html')
    make_summaries_html('All Applications', [
        ('', sd.applications, ['type'], ['Type'])], 'Applications.html')
    make_summaries_html('All Files', [
        ('Config Files', sd.config_files, ['status'], ['Status']),
        ('Other Files', sd.other_files, ['category', 'status'], ['Category', 'Status'])
        ], 'Files.html')
    make_summaries_html('All Scripts', [
        ('', sd.scripts, ['language', 'status'], ['Language', 'Status'])], 'Scripts.html')
    make_capability_summaries_html(sd.capabilities)
    make_summaries_html('All Automatic Checks', [
        ('', sd.automatic_checks, ['last_run', 'status'], ['Last Run', 'Status'])], 'Checks.html')

    for actor in sd.users.values():
        make_actor_html(actor, "User", False)
    for actor in sd.user_groups.values():
        make_actor_html(actor, "User Group", True)
    for actor in sd.hosts.values():
        make_actor_html(actor, "Host", False)
    for actor in sd.host_groups.values():
        make_actor_html(actor, "Host Group", True)

    for capability in sd.capabilities:
        make_capability_html(capability)

    for component in sd.applications.values():
        make_component_html(component, "Application")
    for component in sd.config_files.values():
        make_component_html(component, "Config File")
    for component in sd.other_files.values():
        make_component_html(component, "Other File")
    for component in sd.scripts.values():
        make_component_html(component, "Script")

    for check in sd.automatic_checks.values():
        make_automatic_check_html(check, "Check")


def create_parser():
    """Creates the definition of the expected command line flags."""
    parser = argparse.ArgumentParser(
        description='Site management website creation script.',
        epilog='Copyright Jody Sankey 2011-2020')
    parser.add_argument('destination', type=str,
                        help="The variable subdirectory to write the output.")
    parser.add_argument('-f', '--force', action='store_true',
                        help="Output site even if repo is not currently sychronized.")
    return parser


if __name__ == '__main__':
    make_everything(create_parser().parse_args())
