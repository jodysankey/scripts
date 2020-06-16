#!/usr/bin/python3
# -*- coding: utf-8 -*-

##========================================================
# Copyright Jody M Sankey 2010-2011
#========================================================
# AppliesTo: linux
# RemoveExtension: True
# PublicPermissions: True
#========================================================

""" Python script to translate GnuCash XML file into  a user friendly HTML report.

All data is driven by the first budget found in the input file. The accounts with a budget
are treated as control accounts, for tracking the total spend in any child accounts. The months
shown are driven exclusively by the budget, although current date is used to determine what
should be drawn as 'Future'.

To provide interactive graphics with SVG, XHTML is used and therefore the output file is XHTML
and must be saved with an XML extension. Output is designed for Firefox."""

import os.path
import sys
import xml.etree.ElementTree
from datetime import date, timedelta
from xml.sax.saxutils import escape
import tagwriter


def print_usage():
    """Print standard help string then quit"""
    ver = sys.version_info
    print("\nUsage: gnucashhtml MODE GNUCASHFILE HTMLFILE")
    print("       MODE = 'budget'")
    print("(c)2010 Jody Sankey, currently running in Python v{}.{}.{}\n".format(*ver))
    sys.exit()


def throw_error(text):
    """Output an error message then quit"""
    print("ERROR: " + text)
    sys.exit(1)


def unrationalize(fraction):
    """Return a floating point representation of the input rational fraction string"""
    (numerator, denominator) = fraction.split("/")
    return float(numerator)/float(denominator)


class SpendAccount:
    """Simple class to store data for each exdenditure tracking account."""
    def __init__(self, uid, periods, name, path, control_account):
        self.uid = uid
        self.path = path
        self.name = name
        self.control_account = control_account
        self.expenditures = [0 for i in range(periods)] #@UnusedVariable
        self.transactions = [[] for i in range(periods)] #@UnusedVariable


class ControlAccount:
    """Simple class to store data for each budgeted Account."""
    def __init__(self, uid, periods):
        self.uid = uid
        self.name = ''
        self.sas = []
        self.budgets = [0 for i in range(periods)] #@UnusedVariable
        self.expenditures = [0 for i in range(periods)] #@UnusedVariable

    def __str__(self):
        ret = "Budget '{}' (UID={})\n  ".format(self.name, self.uid)
        for i in range(len(self.budgets)):
            ret += "[{},{}]".format(self.budgets[i], self.expenditures[i])
        return ret


class MonthSet:
    """Simple class to represent a contiguous set of months."""
    def __init__(self, start_str, count):
        start_date = date(int(start_str[0:4]), int(start_str[5:7]), 1)
        e_y, e_m = start_date.year, start_date.month + count
        while e_m > 12:
            e_m -= 12
            e_y += 1
        end_date = date(e_y, e_m, 1) - timedelta(days=1)
        self.dates = (start_date, end_date)
        self.strings = (start_date.isoformat(), end_date.isoformat())
        self.count = count
        self.__yearplusmonth = start_date.year*12 + start_date.month

    def in_range(self, date_str):
        """Returns true iff a supplied date falls within this MonthSet."""
        return self.strings[0] <= date_str <= self.strings[1]

    def column(self, date_str):
        """Returns a zero based month index for the supplied date."""
        return int(date_str[0:4])*12 + int(date_str[5:7]) - self.__yearplusmonth

    def column_names(self):
        """Returns a list of the names for all months in this set."""
        fmt = '%b' if self.count <= 12 else '%b %Y'
        return [(self.dates[0] + timedelta(days=31*x)).strftime(fmt) for x in range(0, self.count)]


CSS_TEXT = """
<style type="text/css">
    html {margin:0px;padding:0px;max-height:100%;height:100%;width:100%;overflow:hidden}
    body {background:#DDDDDD;margin:0px;padding:0px;max-height:100%;height:100%;width:100%}
    h1, h2, th, td {font-family:sans-serif;color:black;text-align:left;margin-top:10px;margin-bottom:0px;}

    th, td {padding:3px;}
    th {font-size:11pt;font-weight:bold;}

    table.mainTable {height:100%;width:100%}
    td.titleHolder,td.dataTableHolder,td.auxiliaryHolder,td.padHolder {padding:8px;border:none}

    td.dataTableHolder {}
    table.dataTable {border-spacing: 10px; height:100%;width:100%;border-spacing:4px;border:outset 4px black;background:DimGrey}
    .dataTable th {background:#222222;border:1px solid LightGray;color:white;}
    .dataTable th.right {text-align:right;}
    .dataTable th.center {text-align:center;}
    .dataTable td {border:1px solid LightGray;text-align:right;background:black}
    .dataTable td.blank {background:DimGrey;width:0px;height:0px;padding:0px;border:none}
    .dataTable td.center {text-align:center;}

    td.auxiliaryHolder {width:90%;height:100%;overflow:hidden}
    table.auxiliaryTable {height:100%;width:100%;overflow:hidden;border-spacing:0px;border:outset 4px black}
    .auxiliaryTable td {font-size:8pt;vertical-align:top;text-align:left;background:white;border:none;padding:5px;}
    .auxiliaryTable h2 {margin-top:10px;margin-bottom:0px;}

    svg {width:100%;height:100%;border:none}
    text {font-family:sans-serif;font-size:8pt;fill:black;stroke:none}

    circle, path {fill-opacity:1;shape-rendering:geometricPrecision;stroke-linejoin:round;stroke-width:2;stroke:black;}
    rect.key {stroke-linejoin:round; stroke-width: 2;stroke:black}
    rect.good {fill-opacity:1;stroke-linejoin:miter; stroke-width: 2;stroke:black; fill:#99FF66}
    rect.bad {fill-opacity:1;stroke-linejoin:miter; stroke-width: 2;stroke:black; fill:#FFB266}
    rect.unmeasurable {fill-opacity:1;stroke-linejoin:round; stroke-width: 2;stroke:black; fill:#66CBFF}

    circle.shadow, rect.shadow {fill: black; fill-opacity:0.6; stroke:none;filter:url(#dropshadow)}

    line {stroke-linejoin:miter;stroke-width:2;stroke:black;}
    line.budget {stroke-width:3;stroke:#CC0000;}


    td.padHolder {height:99%;color:#DDDDDD}

    p {font-family:sans-serif;color:white;font-size:11pt;margin-top:1px;margin-bottom:1px}
    p.overm_overy {color:#FF00FF;}
    p.overm {color:#DD8800;}
    p.overy {color:#FF0000;}
    p.good {color:#22FF22;}
    p.future {color:#BBBBBB;}
    p.bud_real {font-size:8pt;color:#00CCFF;}
    p.bud_none {font-size:8pt;visibility:hidden;}
    p.bud_future {font-size:8pt;color:#BBBBBB;}
</style>
"""

JS_TEXT = """
var hiRow = -1;
var hiCol = -1;
var cellCol = "#000000";
var hdrCol = "#222222";
var highCol = "#777722";
var colors = ['#FF6666','#990F0F','#FFB266','#99540F','#FFFF44','#99990F','#99FF66','#3D990F','#66FFFF','#0F9982','#66CBFF','#0F5499','#CC66FF','#540F99','#FF66CC','#990F54'];

function clearSelect()
{
    var tbl = document.getElementById('dataTable');
    if(hiRow>=0 && hiCol>=0)
    {
        tbl.rows[hiRow+1].cells[hiCol+1].style.backgroundColor = cellCol;
        tbl.rows[hiRow+1].cells[0].style.backgroundColor = hdrCol;
        tbl.rows[0].cells[hiCol+1].style.backgroundColor = hdrCol;
        hiRow = -1; hiCol = -1;
    }
    else if(hiRow>=0)
    {
        tbl.rows[hiRow+1].cells[0].style.backgroundColor = hdrCol;
        for(var i=1 ; i<months.length+1; i++)
            tbl.rows[hiRow+1].cells[i].style.backgroundColor = cellCol;
        tbl.rows[hiRow+1].cells[months.length+2].style.backgroundColor = cellCol;
        hiRow = -1;
    }
    else if(hiCol>=0)
    {
        tbl.rows[0].cells[hiCol+1].style.backgroundColor = hdrCol;
        for(var i=1 ; i<accounts.length+1; i++)
            tbl.rows[i].cells[hiCol+1].style.backgroundColor = cellCol;
        tbl.rows[accounts.length+2].cells[hiCol+1].style.backgroundColor = cellCol;
        hiCol = -1;
    }
    else
    {
        return;
    }

    var trans = document.getElementById('auxiliaryHolder');
    trans.innerHTML = "";

}

function selectCell(row,col)
{
    clearSelect();

    var tbl = document.getElementById('dataTable');
    hiRow = row;
    hiCol = col;
    tbl.rows[hiRow+1].cells[hiCol+1].style.backgroundColor = highCol;
    tbl.rows[0].cells[hiCol+1].style.backgroundColor = highCol;
    tbl.rows[hiRow+1].cells[0].style.backgroundColor = highCol;

    var str = ""
    if(transactions[row][col].length>0)
    {
        str = "<table class='auxiliaryTable'>"
        for(var i=0 ; i<transactions[row][col].length; i++)
        {
            str += "<tr><td colspan='2'><h2>" + transactions[row][col][i][0] + "</h2></td>"
            str += "<td colspan='2'><h2 style='text-align:right'>" + transactions[row][col][i][1] + "</h2></td></tr>"

            for(var j=0 ; j<transactions[row][col][i][2].length; j++)
            {
                str += "<tr><td>" + transactions[row][col][i][2][j][0] + "</td>"
                str += "<td>" + transactions[row][col][i][2][j][1] + "</td>"
                str += "<td>" + transactions[row][col][i][2][j][2] + "</td>"
                str += "<td style='text-align:right'>" + transactions[row][col][i][2][j][3] + "</td></tr>"
            }
        }
        str += "<tr><td colspan='4' style='height:99%;'> </td></tr></table>"
    }

    var trans = document.getElementById('auxiliaryHolder');
    trans.innerHTML = str;
}


function svgStartString(w,h)
{
    // Creates a string to start our svg element with a viewport of the specified size

    // Firefox 3.6.13 appears buggy in that a 100% SVG in 100% td, table, body, and html will still grow higher than the screen
    // to fit the width into the available space. Spent quite a while on this.
    // A crude but actually pretty good technique is to hardcode the hight in pixels with Javascript as the graph is drawn. User can't
    // resize the window without causing the graph to be deselected anyway

    var trans = document.getElementById('auxiliaryHolder');

    return '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet" ' +
           'style="height:' + (trans.clientHeight-20) + 'px;width:' + (trans.clientWidth-20) + 'px">' +
           '<defs><filter id="dropshadow" width="150%" height="150%"><feGaussianBlur stdDeviation="2"/></filter>' +
           '<marker id="endArrow" viewBox="0 0 10 10" refX="1" refY="5" markerUnits="strokeWidth" orient="auto" markerWidth="5" markerHeight="4">' +
           '<polyline points="0,0 10,5 0,10 1,5"/></marker></defs>';
}


function drawPieChart(names,values)
{

    //First Calculate the total values of the pie
    var total = 0.0;
    var count = 0;
    for(var i=0;i<values.length;i++)
    {
        total += values[i];
        if(values[i]>=0.01)count++;
    }

    var str = "";
    var trans = document.getElementById('auxiliaryHolder');

    //Only draw if the total exceeds zero
    if(total>=0.01)
    {
        str = svgStartString(250, 270 + count*15);
        str += '<circle cx="130" cy="130" r="100" class="shadow"/>';

        //Now draw each slice
        var lastAngle = 0.0;
        var lastPoint = [225,125]
        var angle = 0.0;
        var point;
        var ypos = 250;
        for(var i=0;i<values.length;i++)
        {

            if(values[i]>=0.01)
            {
                color = (values.length*2<=colors.length) ? colors[2*i] : colors[i % colors.length];
                angle = lastAngle + values[i]/total*2.0*Math.PI;

                if(count==1)
                {
                    //Draw one segment pies as a simple circle
                    str += '<circle cx="125" cy="125" r="100" style="fill:' + color + '"/>';
                }
                else
                {
                    //Draw a regular pie slice
                    point = [125 + Math.round(100.0 * Math.cos(angle)), 125 - Math.round(100.0 * Math.sin(angle))];
                    str += '<path d="M125,125 L' + lastPoint[0] + ',' + lastPoint[1] + ' A100,100 0 ' + ((angle-lastAngle)>Math.PI || values.length==1 ? '1' : '0') +
                           ',0 ' + point[0] + ',' + point[1] + ' z" style="fill:' + color + '"/>';
                }

                //Include a key if this segment has a value
                str += '<rect x="10" y="' + (ypos-8) + '" width="8" height="8" class="key" style="fill:' + color + '"/>'
                str += '<text x="25"  y="' + (ypos) + '" class="svgLeft">' + names[i] + '</text>';
                str += '<text text-anchor="end" x="230" y="' + (ypos) + '">$' + values[i].toFixed(2) + '</text>';
                ypos += 15

                lastAngle = angle;
                lastPoint = point;
            }
        }
        str += '</svg>';
    }

    trans.innerHTML = str;
}


function calcLimits(min,max)
{
    // Return the end points of an axis which encapsulates the specified range,
    // along with the step size
    var range = max-min;

    var order = Math.ceil((Math.log(range)*Math.LOG10E));
    var factor = range/Math.pow(10.0,order);
    var step = Math.pow(10.0,order)*(factor>0.5 ? 0.2 : (factor>0.2 ? 0.1 : 0.05));

    var output = [0.0,0.0,step];
    if(min<0.01) output[0] = step * Math.floor(min/step);
    if(max>0.01) output[1] = step * Math.ceil(max/step);

    return output;
}


function drawBarGraph(names,budgets,expenditures,nibbleBudget)
{
    //If we're asked to nibble away the budget based on expenditure, do this now
    if(nibbleBudget)
    {
        var newBudgets = [budgets[0]];
        var remaining = budgets[0];

        for(var i=1; i<budgets.length; i++)
        {
            remaining -= expenditures[i-1];
            if(remaining < 0.0) remaining = 0.0;
            newBudgets.push(remaining);
        }
        budgets = newBudgets;
    }

    var trans = document.getElementById('auxiliaryHolder');

    //Now decide what the min and max scales should be
    var min = 0.0;
    var max = 0.0;
    for(var i=0; i<budgets.length; i++)
    {
        if(budgets[i] > max) max = budgets[i];
        if(budgets[i] < min) min = budgets[i];
        if(expenditures[i] > max) max = expenditures[i];
        if(expenditures[i] < min) min = expenditures[i];
    }
    var limits = calcLimits(min,max);

    //No data, dont draw anything
    if(min > -0.01 && max < 0.01)
    {
        trans.innerHTML = "";
        return;
    }

    //Calulate some dimensions
    var Y_BOTTOM = 240.0
    var X_LEFT = 60.0
    var WIDTH = 320.0
    var HEIGHT = 220.0

    var origin = Y_BOTTOM + limits[0]/(limits[1]-limits[0]);
    var scale = -HEIGHT/(limits[1]-limits[0]);
    var catWidth = WIDTH/names.length

    var shadowStr;
    var frontStr;

    //Draw the axes
    frontStr += '<line x1="' + X_LEFT + '" y1="' + Y_BOTTOM + '" x2="' + X_LEFT + '" y2="' + (Y_BOTTOM-HEIGHT)+ '"/>'
    frontStr += '<line x1="' + X_LEFT + '" y1="' + origin + '" x2="' + (X_LEFT+WIDTH) + '" y2="' + origin + '"/>'

    //Label y axis
    for(var val = limits[0]; val<=limits[1]+0.001; val+= limits[2])
    {
        frontStr += '<line x1="' + (X_LEFT-10) + '" y1="' + (scale*val + origin) + '" x2="' + X_LEFT + '" y2="' + (scale*val + origin) + '"/>'
        frontStr += '<text text-anchor="end" x="' + (X_LEFT-20) + '" y="' + (scale*val + origin + 4) + '" class="svgRight">$' + val.toFixed(0) + '</text>';
    }

    //Label x axis and draw each box
    frontStr += '<line x1="' + X_LEFT + '" y1="' + Y_BOTTOM + '" x2="' + X_LEFT + '" y2="' + (Y_BOTTOM+10) + '"/>'
    for(var i = 0; i<names.length; i++)
    {
        frontStr += '<line x1="' + (X_LEFT+(i+1)*catWidth) + '" y1="' + Y_BOTTOM + '" x2="' + (X_LEFT+(i+1)*catWidth) + '" y2="' + (Y_BOTTOM+10) + '"/>'

        var class_name = ((budgets[i]<0.01 && !nibbleBudget) ? 'unmeasurable' : (expenditures[i]>budgets[i] ? 'bad' : 'good'))
        if(expenditures[i]>=0.0)
        {
            frontStr += '<rect x="' + (X_LEFT+(i+0.2)*catWidth) + '" y="' + (origin+scale*expenditures[i]) + '" width="' + (catWidth*0.6) +
                   '" height="' + (-expenditures[i]*scale) + '" class="' + class_name + '"/>'
            shadowStr += '<rect x="' + (X_LEFT+(i+0.2)*catWidth+5) + '" y="' + (origin+scale*expenditures[i]+5) + '" width="' + (catWidth*0.6) +
                   '" height="' + (-expenditures[i]*scale) + '" class="shadow"/>'
        }
        else
        {
            frontStr += '<rect x="' + (X_LEFT+(i+0.2)*catWidth) + '" y="' + origin + '" width="' + (catWidth*0.6) +
                   '" height="' + (expenditures[i]*scale) + '" class="' + class_name + '"/>'
            shadowStr += '<rect x="' + (X_LEFT+(i+0.2)*catWidth+5) + '" y="' + (origin+5) + '" width="' + (catWidth*0.6) +
                   '" height="' + (expenditures[i]*scale) + '" class="shadow"/>'
        }

        if(budgets[i]>=0.01)
            frontStr += '<line class="budget" x1="' + (X_LEFT+i*catWidth) + '" y1="' + (origin + scale*budgets[i]) + '" x2="' + (X_LEFT+(i+1)*catWidth) + '" y2="' + (origin + scale*budgets[i]) + '"/>'

        //Note, wanted to do right align here, but its currently broken for long strings in Firefox
        frontStr += '<text transform="rotate(90,' + X_LEFT + ',' + Y_BOTTOM + ')" x="' + (X_LEFT+10) + '" y="' + (Y_BOTTOM - (i+0.3)*catWidth) + '">' + names[i] + '</text>';
    }

    trans.innerHTML = svgStartString(400, 450) + shadowStr + frontStr + '</svg>';
}


function selectAccountTotal(row)
{
    clearSelect();

    var tbl = document.getElementById('dataTable');
    hiRow = row;
    for(var i=0 ; i<months.length+1; i++)
        tbl.rows[hiRow+1].cells[i].style.backgroundColor = highCol;
    tbl.rows[hiRow+1].cells[months.length+2].style.backgroundColor = highCol;

    var names = [];
    var values = [];
    for(var i=0; i<spend_accounts[row].length; i++)
        if(spend_accounts[row][i][1] >= 0.1)
        {
            names.push(spend_accounts[row][i][0]);
            values.push(spend_accounts[row][i][1]);
        }

    drawPieChart(names,values);
}


function selectMonthTotal(col)
{
    clearSelect();

    var tbl = document.getElementById('dataTable');
    hiCol = col;
    for(var i=0 ; i<accounts.length+1; i++)
        tbl.rows[i].cells[hiCol+1].style.backgroundColor = highCol;
    tbl.rows[accounts.length+2].cells[hiCol+1].style.backgroundColor = highCol;

    var values = [];
    for(var i=0; i<accounts.length; i++)
        values.push(control_accounts[i][col][1]);

    drawPieChart(accounts,values);
}


function selectMonthHeader(col)
{
    clearSelect();

    var tbl = document.getElementById('dataTable');
    hiCol = col;
    for(var i=0 ; i<accounts.length+1; i++)
        tbl.rows[i].cells[hiCol+1].style.backgroundColor = highCol;

    var budgets = [];
    var expenditures = [];
    for(var i=0; i<accounts.length; i++)
    {
        budgets.push(control_accounts[i][col][0]);
        expenditures.push(control_accounts[i][col][1]);
    }

    drawBarGraph(accounts,budgets,expenditures,false);
}


function selectAccountHeader(row)
{
    clearSelect();

    var tbl = document.getElementById('dataTable');
    hiRow = row;
    for(var i=0 ; i<months.length+1; i++)
        tbl.rows[hiRow+1].cells[i].style.backgroundColor = highCol;

    // Gather the data out of the matrix, nibble away the start budget
    // if and only if there are no budget values after first month
    var budgets = [];
    var expenditures = [];
    var nibble = true;
    for(var i=0; i<months.length; i++)
    {
        budgets.push(control_accounts[row][i][0]);
        expenditures.push(control_accounts[row][i][1]);
        if(i>0 && control_accounts[row][i][0]>0.0) nibble = false;
    }

    drawBarGraph(months,budgets,expenditures,nibble);
}
"""


def parse_gnucash_file(filename, control_accounts, control_account_names):
    """Reads data from  specified GNU cash file into account objects

    control_accounts is populated with budgeted account objects hashed by UID
    control_account_names is populated with account UIDs hashed by name
    returns a list of [budgetName, monthSet]"""

    # Read the file and work with the first budget we find
    tree = xml.etree.ElementTree.parse(filename)
    book = tree.getroot()[1]
    budget = book.find('{http://www.gnucash.org/XML/gnc}budget')
    if budget is None:
        throw_error("Could not find budget in file")

    # Gather standard budget naming and timing data
    budget_name = budget.findtext('{http://www.gnucash.org/XML/bgt}name')
    recurrence = budget.find('{http://www.gnucash.org/XML/bgt}recurrence')
    if recurrence.findtext('{http://www.gnucash.org/XML/recurrence}period_type') != 'month':
        throw_error("Budget must be monthly")
    start_str = recurrence.find('{http://www.gnucash.org/XML/recurrence}start')[0].text
    periods = int(budget.findtext('{http://www.gnucash.org/XML/bgt}num-periods'))
    budget_months = MonthSet(start_str, periods)

    # And make a budget object for each thing we find in the budget which actually has a value
    for x_account in list(budget.find('{http://www.gnucash.org/XML/bgt}slots')):
        uid = x_account.findtext('{http://www.gnucash.org/XML/slot}key')
        control_acc = ControlAccount(uid, periods)
        has_value = False
        for x_slot in list(x_account.find('{http://www.gnucash.org/XML/slot}value')):
            control_acc.budgets[int(x_slot[0].text)] = unrationalize(x_slot[1].text)
            if unrationalize(x_slot[1].text) > 1.0: has_value = True
        if has_value:
            control_accounts[uid] = control_acc

    # Now go back and create a hash of all the spend accounts which contribute to one of these
    # control accounts, adding names to the control accounts, and creating a reverse hash
    spend_accounts = {}

    for x_account in book.findall('{http://www.gnucash.org/XML/gnc}account'):
        a_id = x_account.findtext('{http://www.gnucash.org/XML/act}id')
        p_id = x_account.findtext('{http://www.gnucash.org/XML/act}parent')
        name = x_account.findtext('{http://www.gnucash.org/XML/act}name')

        if a_id in control_accounts:
            # This exactly matches the control account
            control_account_names[name] = a_id
            control_accounts[a_id].name = name
            spend_acc = SpendAccount(a_id, periods, 'Uncategorized', '', control_accounts[a_id])
            spend_accounts[a_id] = spend_acc
            control_accounts[a_id].sas.append(spend_acc)
        elif p_id in spend_accounts:
            # This is a child of something which was already covered
            parent = spend_accounts[p_id]
            spend_acc = SpendAccount(a_id,
                                     periods,
                                     name,
                                     name if parent.path == '' else parent.path + "/" + name,
                                     parent.control_account)
            spend_accounts[a_id] = spend_acc
            parent.control_account.sas.append(spend_acc)

    # Finally ready to process each transaction
    for x_trans in book.findall('{http://www.gnucash.org/XML/gnc}transaction'):
        date_str = x_trans.find('{http://www.gnucash.org/XML/trn}date-posted')[0].text[:10]

        #Check transaction is in date
        if budget_months.in_range(date_str):

            # Yes, gather common info
            desc = x_trans.findtext('{http://www.gnucash.org/XML/trn}description') or ''
            notes = None
            col = budget_months.column(date_str)
            if x_trans.find('{http://www.gnucash.org/XML/trn}slots') is not None:
                for x_slot in list(x_trans.find('{http://www.gnucash.org/XML/trn}slots')):
                    if x_slot[0].text == 'notes':
                        notes = x_slot[1].text
                        break

            # Look for splits we care about
            for x_split in list(x_trans.find('{http://www.gnucash.org/XML/trn}splits')):
                account = spend_accounts.get(
                    x_split.findtext('{http://www.gnucash.org/XML/split}account'))
                if account is not None:
                    memo = x_split.findtext('{http://www.gnucash.org/XML/split}memo')
                    if notes and memo:
                        memo = "{} / {}".format(notes, memo)
                    value = unrationalize(
                        x_split.findtext('{http://www.gnucash.org/XML/split}value'))
                    # Tally expenditure at both the spend account and control account,
                    # track transactions at spend account
                    account.expenditures[col] += value
                    account.control_account.expenditures[col] += value
                    account.transactions[col].append(
                        [date_str, value, desc, memo if memo else notes])

    # Close the XML document
    tree = None

    # Sort all transaction lists by date
    for acc in spend_accounts.values():
        for trnlist in acc.transactions:
            try:
                trnlist.sort()
            except TypeError as err:
                print('ERROR sorting Account "{}" ({})'.format(acc.name, err))
                print('\n'.join(['   ' + str(t) for t in trnlist]))
                sys.exit(1)

    # Return the title and monthSet
    return (budget_name, budget_months)


def create_totals_and_styles(accounts, account_names, months):
    """Summarizes totals and style names a hash of account objects.

    returns a list of [account_totals, month_totals, grand_totals, styles]"""

    # Create a matrix of styles based on over/under spend, and vectors for the totals
    account_totals = [[0, 0, 0] for i in range(len(accounts.keys()))] #@UnusedVariable
    month_totals = [[0, 0] for i in range(months.count)] #@UnusedVariable
    styles = [[['none', 'none'] for i in range(months.count)] for j in accounts] #@UnusedVariable

    today_col = months.column(date.today().isoformat())

    row = 0
    for name in sorted(account_names):
        account = accounts[account_names[name]]
        totals = [0.0, 0.0, 0.0]

        for col in range(months.count):
            totals[0] += account.expenditures[col]
            totals[1] += account.budgets[col]
            if col <= today_col:
                totals[2] += (account.budgets[col] - account.expenditures[col])
            month_totals[col][0] += account.expenditures[col]
            month_totals[col][1] += account.budgets[col]
            if account.expenditures[col] > account.budgets[col] and account.budgets[col] > 0:
                if totals[2] < 0:
                    styles[row][col][0] = 'overm_overy'
                else:
                    styles[row][col][0] = 'overm'
            else:
                if totals[0] > totals[1]:
                    styles[row][col][0] = 'overy'
                elif col <= today_col:
                    styles[row][col][0] = 'good'
                else:
                    styles[row][col][0] = 'future'
            if account.budgets[col] < 0.01:
                styles[row][col][1] = 'bud_none'
            elif col > today_col:
                styles[row][col][1] = 'bud_future'
            else:
                styles[row][col][1] = 'bud_real'

        account_totals[row] = totals
        row += 1

    grand_totals = [sum([x[i] for x in account_totals]) for i in range(3)]

    return [account_totals, month_totals, grand_totals, styles]


def write_html(filename, title, accounts, account_names, account_totals,
               months, month_totals, grand_totals, styles):
    """Writes the supplied account data out as HTML at the specified filename."""

    # Open our output document
    wt = tagwriter.TagWriter(filename)

    # Output HTML header, including embedded Javascript and CSV
    wt.open("html", 'xmlns="http://www.w3.org/1999/xhtml"')
    wt.open("head")
    wt.write("title", '', title)
    wt.write_text(CSS_TEXT)
    wt.open("script", 'type="text/javascript"')
    wt.write_text("// <![CDATA[\n\n")
    wt.write_text("var periods = {};\n".format(months.count))
    wt.write_text("var accounts = {};\n".format(len(accounts.keys())))

    # JavaScript account array
    # ========================
    # > 1D array of control_account names
    wt.write_text("var accounts = [")
    for name in sorted(account_names.keys()):
        wt.write_text("'{}',".format(escape(name)))
    wt.write_text("];\n")

    # JavaScript month array
    # ========================
    # > 1D array of month names
    wt.write_text("var months = [")
    for month in months.column_names():
        wt.write_text("'{}',".format(month))
    wt.write_text("];\n")

    # JavaScript control_account matrix
    # =================================
    # > 2D matrix of (control_account) x (month)
    # > Where each entry contains [budget, expenditure]
    wt.write_text("var control_accounts = [\n")
    for name in sorted(account_names):
        account = accounts[account_names[name]]
        wt.write_text("[")
        for col in range(0, months.count):
            wt.write_text("[{},{}],".format(account.budgets[col], account.expenditures[col]))
        wt.write_text("],\n")
    wt.write_text("];\n")

    # JavaScript spend_account matrix
    # =================================
    # > 2D matrix of (control_account) x (spend_account)
    # > Where each entry contains total [spend_account_name,expenditure]
    wt.write_text("var spend_accounts = [\n")
    for name in sorted(account_names):
        account = accounts[account_names[name]]
        wt.write_text("[")
        for spnd in account.sas:
            wt.write_text("['{}',{}],".format(spnd.name, sum(spnd.expenditures)))
        wt.write_text("],\n")
    wt.write_text("];\n")

    # JavaScript transaction matrix
    # =============================
    # > 3D matrix of (control_account) x (month) x (spend_account)
    # > Where each entry contains [spend_account name, total value, transaction list]
    # > Each transaction is in the form [date, desc, memo, value]
    # > Only spend_accounts which actually contain transactions are included
    wt.write_text("var transactions = [\n")
    for name in sorted(account_names.keys()):
        wt.write_text("[\n")
        account = accounts[account_names[name]]

        for col in range(months.count):
            wt.write_text("[")
            for spnd in account.sas:
                if spnd.transactions[col]:
                    wt.write_text("['{}','${:.2f}',[".format(spnd.name, spnd.expenditures[col]))
                    for trn in spnd.transactions[col]:
                        #print(trn)
                        wt.write_text("['{}',".format(trn[0]))
                        wt.write_text("'{}','{}',".format(
                            *['' if not x else escape(x.replace("'", "\\'")) for x in trn[2:4]]))
                        wt.write_text("'${:.2f}'],".format(trn[1]))
                    wt.write_text("]],")
            wt.write_text("],\n")
        wt.write_text("],\n")
    wt.write_text("];\n")

    wt.write_text(JS_TEXT)
    wt.write_text("// ]]>\n")
    wt.close()
    wt.close()

    wt.open("body")

    wt.open('table', 'class="mainTable"')
    wt.open('tr')
    wt.open('td')
    wt.open('table', 'style="height:100%"')

    #Title
    wt.open('tr')
    wt.open('td', 'class="titleHolder"')
    wt.write("h1", '', title)
    wt.close()
    wt.close()
    wt.open('tr')
    wt.open('td', 'class="dataTableHolder"')

    wt.open('table', 'class="dataTable" id="dataTable" onmouseout="clearSelect()"')

    #Table header
    wt.open("tr")
    wt.write("td", 'class="blank"')
    i = 0
    for month in months.column_names():
        wt.write('th', 'class="center" onmouseover="selectMonthHeader({})"'.format(i), month)
        i += 1
    wt.write('td', 'class="blank"')
    wt.write('th', 'class="center"', "Totals")
    wt.write('th', "", "Remaining")
    wt.close()

    # One row per account
    row = 0
    for name in sorted(account_names):
        account = accounts[account_names[name]]

        wt.open("tr")
        wt.write("th",
                 'class="right" onmouseover="selectAccountHeader({})"'.format(row), escape(name))
        for col in range(0, months.count):
            wt.open("td", 'onmouseover="selectCell({},{})"'.format(row, col))
            wt.write("p", "class='{}'".format(styles[row][col][0]), "${:.0f}".format(
                account.expenditures[col]))
            wt.write("p", "class='{}'".format(styles[row][col][1]), "${:.0f}".format(
                account.budgets[col]))
            wt.close()

        wt.write("td", 'class="blank"')
        wt.open("td", 'onmouseover="selectAccountTotal({})"'.format(row))
        wt.write("p",
                 "class='{}'".format(
                     'overy' if account_totals[row][0] > account_totals[row][1] else 'good'),
                 "${:.0f}".format(account_totals[row][0]))
        wt.write("p", "class='bud_real'", "${:.0f}".format(account_totals[row][1]))
        wt.close()
        wt.open("td", 'class="center"')
        wt.write("p",
                 "class='{}'".format('overy' if account_totals[row][2] < 0 else 'good'),
                 "${:.2f}".format(account_totals[row][2]))
        wt.close()
        wt.close()
        row += 1

    wt.open("tr")
    for col in range(0, months.count+4):
        wt.write("td", 'class="blank"')
    wt.close()

    # One row for totals
    wt.open("tr")
    wt.write("th", 'class="right"', "Totals")
    for col in range(0, months.count):
        wt.open('td', 'onmouseover="selectMonthTotal({})"'.format(col))
        wt.write(
            "p",
            "class='{}'".format('overy' if month_totals[col][0] > month_totals[col][1] else 'good'),
            "${:.0f}".format(month_totals[col][0]))
        wt.write("p", "class='bud_real'", "${:.0f}".format(month_totals[col][1]))
        wt.close()
    wt.write("td", 'class="blank"')
    wt.open("td")
    wt.write("p", "class='{}'".format('overy' if grand_totals[0] > grand_totals[1] else 'good'),
             "${:.0f}".format(grand_totals[0]))
    wt.write("p", "class='bud_real'", "${:.0f}".format(grand_totals[1]))
    wt.close()
    wt.open("td", 'class="center"')
    wt.write("p", "class='{}'".format('overy' if grand_totals[2] < 0 else 'good'),
             "${:.2f}".format(grand_totals[2]))
    wt.close()
    wt.close()

    # Close data table, cell and row
    wt.close()
    wt.close()
    wt.close()

    #Padding cell
    wt.open('tr')
    wt.write('td', 'class="padHolder"')
    wt.close()

    wt.close() #Table holding Title/Data/Pad
    wt.close()

    # Holding area for extra information
    wt.write('td', 'class="auxiliaryHolder" id="auxiliaryHolder"')

    wt.close() #Tr
    wt.close() #MainTable
    wt.close() #Body
    wt.close() #Html


def main():
    """Executes the script using command line inputs."""

    # Just print usage if no arguments supplied
    if len(sys.argv) != 4:
        print_usage()

    # Determine the filenames
    mode = sys.argv[1]
    in_name = sys.argv[2]
    out_name = sys.argv[3]

    # Check the mode is valid
    if mode != 'budget':
        throw_error("Mode {} is not valid".format(mode))
    # Check the file exists
    if not os.path.isfile(in_name):
        throw_error("File does not exist")
    # Check the lock does not exist
    if os.path.isfile(in_name + ".LCK"):
        throw_error("File appears to be locked, please close GnuCash first")

    # Parse the GNU cash file
    accounts = {}
    account_names = {}
    (budget_name, months) = parse_gnucash_file(in_name, accounts, account_names)

    # Create a matrix of styles based on over/under spend, and vectors for the totals
    [account_totals, month_totals, grand_totals, styles] = create_totals_and_styles(
        accounts=accounts, account_names=account_names, months=months)

    # And write to HTML
    title = os.path.basename(in_name) + " " + budget_name + " @ " + date.today().isoformat()
    write_html(out_name, title, accounts, account_names, account_totals,
               months, month_totals, grand_totals, styles)


if __name__ == '__main__':
    main()
