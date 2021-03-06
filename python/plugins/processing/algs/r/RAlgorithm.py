# -*- coding: utf-8 -*-

"""
***************************************************************************
    RAlgorithm.py
    ---------------------
    Date                 : August 2012
    Copyright            : (C) 2012 by Victor Olaya
    Email                : volayaf at gmail dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from future import standard_library
standard_library.install_aliases()
from builtins import str

__author__ = 'Victor Olaya'
__date__ = 'August 2012'
__copyright__ = '(C) 2012, Victor Olaya'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import json

from qgis.core import QgsApplication

from processing.core.GeoAlgorithm import GeoAlgorithm
from processing.core.GeoAlgorithmExecutionException import GeoAlgorithmExecutionException
from processing.core.ProcessingLog import ProcessingLog
from processing.gui.Help2Html import getHtmlFromHelpFile
from processing.core.parameters import ParameterRaster
from processing.core.parameters import ParameterTable
from processing.core.parameters import ParameterVector
from processing.core.parameters import ParameterMultipleInput
from processing.core.parameters import ParameterString
from processing.core.parameters import ParameterNumber
from processing.core.parameters import ParameterBoolean
from processing.core.parameters import ParameterSelection
from processing.core.parameters import ParameterTableField
from processing.core.parameters import ParameterExtent
from processing.core.parameters import ParameterCrs
from processing.core.parameters import ParameterFile
from processing.core.outputs import OutputTable
from processing.core.outputs import OutputVector
from processing.core.outputs import OutputRaster
from processing.core.outputs import OutputHTML
from processing.core.parameters import getParameterFromString
from processing.core.outputs import getOutputFromString
from processing.tools import dataobjects
from processing.tools.system import isWindows
from processing.script.WrongScriptException import WrongScriptException
from .RUtils import RUtils

pluginPath = os.path.normpath(os.path.join(
    os.path.split(os.path.dirname(__file__))[0], os.pardir))


class RAlgorithm(GeoAlgorithm):

    R_CONSOLE_OUTPUT = 'R_CONSOLE_OUTPUT'
    RPLOTS = 'RPLOTS'

    def getCopy(self):
        newone = RAlgorithm(self.descriptionFile)
        newone.provider = self.provider
        return newone

    def __init__(self, descriptionFile, script=None):
        GeoAlgorithm.__init__(self)
        self.script = script
        self.descriptionFile = descriptionFile
        if script is not None:
            self.defineCharacteristicsFromScript()
        if descriptionFile is not None:
            self.defineCharacteristicsFromFile()
        self._icon = None

    def getIcon(self):
        if self._icon is None:
            self._icon = QgsApplication.getThemeIcon("/providerR.svg")
        return self._icon

    def defineCharacteristicsFromScript(self):
        lines = self.script.split('\n')
        self.name, self.i18n_name = self.trAlgorithm('[Unnamed algorithm]')
        self.group, self.i18n_group = self.trAlgorithm('User R scripts')
        self.parseDescription(iter(lines))

    def defineCharacteristicsFromFile(self):
        filename = os.path.basename(self.descriptionFile)
        self.name = filename[:filename.rfind('.')].replace('_', ' ')
        self.group, self.i18n_group = self.trAlgorithm('User R scripts')
        with open(self.descriptionFile, 'r') as f:
            lines = [line.strip() for line in f]
        self.parseDescription(iter(lines))

    def parseDescription(self, lines):
        self.script = ''
        self.commands = []
        self.showPlots = False
        self.showConsoleOutput = False
        self.useRasterPackage = True
        self.passFileNames = False
        self.verboseCommands = []
        ender = 0
        line = next(lines).strip('\n').strip('\r')
        while ender < 10:
            if line.startswith('##'):
                try:
                    self.processParameterLine(line)
                except Exception:
                    raise WrongScriptException(
                        self.tr('Could not load R script: {0}.\n Problem with line {1}').format(self.descriptionFile, line))
            elif line.startswith('>'):
                self.commands.append(line[1:])
                self.verboseCommands.append(line[1:])
                if not self.showConsoleOutput:
                    self.addOutput(OutputHTML(RAlgorithm.R_CONSOLE_OUTPUT,
                                              self.tr('R Console Output')))
                self.showConsoleOutput = True
            else:
                if line == '':
                    ender += 1
                else:
                    ender = 0
                self.commands.append(line)
            self.script += line + '\n'
            try:
                line = next(lines).strip('\n').strip('\r')
            except:
                break

    def getVerboseCommands(self):
        return self.verboseCommands

    def createDescriptiveName(self, s):
        return s.replace('_', ' ')

    def processParameterLine(self, line):
        param = None
        line = line.replace('#', '')
        if line.lower().strip().startswith('showplots'):
            self.showPlots = True
            self.addOutput(OutputHTML(RAlgorithm.RPLOTS, 'R Plots'))
            return
        if line.lower().strip().startswith('dontuserasterpackage'):
            self.useRasterPackage = False
            return
        if line.lower().strip().startswith('passfilenames'):
            self.passFileNames = True
            return
        tokens = line.split('=')
        desc = self.createDescriptiveName(tokens[0])
        if tokens[1].lower().strip() == 'group':
            self.group = self.i18n_group = tokens[0]
            return
        if tokens[1].lower().strip() == 'name':
            self.name = self.i18n_name = tokens[0]
            return

        out = getOutputFromString(line)
        if out is None:
            param = getParameterFromString(line)

        if param is not None:
            self.addParameter(param)
        elif out is not None:
            out.name = tokens[0]
            out.description = desc
            self.addOutput(out)
        else:
            raise WrongScriptException(
                self.tr('Could not load script: {0}.\n'
                        'Problem with line "{1}"', 'ScriptAlgorithm').format(self.descriptionFile or '', line))

            raise WrongScriptException(
                self.tr('Could not load R script: {0}.\n Problem with line {1}').format(self.descriptionFile, line))

    def processAlgorithm(self, feedback):
        if isWindows():
            path = RUtils.RFolder()
            if path == '':
                raise GeoAlgorithmExecutionException(
                    self.tr('R folder is not configured.\nPlease configure it '
                            'before running R scripts.'))
        loglines = []
        loglines.append(self.tr('R execution commands'))
        loglines += self.getFullSetOfRCommands()
        for line in loglines:
            feedback.pushCommandInfo(line)
        ProcessingLog.addToLog(ProcessingLog.LOG_INFO, loglines)
        RUtils.executeRAlgorithm(self, feedback)
        if self.showPlots:
            htmlfilename = self.getOutputValue(RAlgorithm.RPLOTS)
            with open(htmlfilename, 'w') as f:
                f.write('<html><img src="' + self.plotsFilename + '"/></html>')
        if self.showConsoleOutput:
            htmlfilename = self.getOutputValue(RAlgorithm.R_CONSOLE_OUTPUT)
            with open(htmlfilename, 'w') as f:
                f.write(RUtils.getConsoleOutput())

    def getFullSetOfRCommands(self):
        commands = []
        commands += self.getImportCommands()
        commands += self.getRCommands()
        commands += self.getExportCommands()

        return commands

    def getExportCommands(self):
        commands = []
        for out in self.outputs:
            if isinstance(out, OutputRaster):
                value = out.value
                value = value.replace('\\', '/')
                if self.useRasterPackage or self.passFileNames:
                    commands.append('writeRaster(' + out.name + ',"' + value +
                                    '", overwrite=TRUE)')
                else:
                    if not value.endswith('tif'):
                        value = value + '.tif'
                    commands.append('writeGDAL(' + out.name + ',"' + value +
                                    '")')
            elif isinstance(out, OutputVector):
                value = out.value
                if not value.endswith('shp'):
                    value = value + '.shp'
                value = value.replace('\\', '/')
                filename = os.path.basename(value)
                filename = filename[:-4]
                commands.append('writeOGR(' + out.name + ',"' + value + '","' +
                                filename + '", driver="ESRI Shapefile")')
            elif isinstance(out, OutputTable):
                value = out.value
                value = value.replace('\\', '/')
                commands.append('write.csv(' + out.name + ',"' + value + '")')

        if self.showPlots:
            commands.append('dev.off()')

        return commands

    def getImportCommands(self):
        commands = []

        # Just use main mirror
        commands.append('options("repos"="http://cran.at.r-project.org/")')

        # Try to install packages if needed
        if isWindows():
            commands.append('.libPaths(\"' + str(RUtils.RLibs()).replace('\\', '/') + '\")')
        packages = RUtils.getRequiredPackages(self.script)
        packages.extend(['rgdal', 'raster'])
        for p in packages:
            commands.append('tryCatch(find.package("' + p +
                            '"), error=function(e) install.packages("' + p +
                            '", dependencies=TRUE))')
        commands.append('library("raster")')
        commands.append('library("rgdal")')

        for param in self.parameters:
            if isinstance(param, ParameterRaster):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    value = param.value
                    value = value.replace('\\', '/')
                    if self.passFileNames:
                        commands.append(param.name + ' = "' + value + '"')
                    elif self.useRasterPackage:
                        commands.append(param.name + ' = ' + 'brick("' + value + '")')
                    else:
                        commands.append(param.name + ' = ' + 'readGDAL("' + value + '")')
            elif isinstance(param, ParameterVector):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    value = param.getSafeExportedLayer()
                    value = value.replace('\\', '/')
                    filename = os.path.basename(value)
                    filename = filename[:-4]
                    folder = os.path.dirname(value)
                    if self.passFileNames:
                        commands.append(param.name + ' = "' + value + '"')
                    else:
                        commands.append(param.name + ' = readOGR("' + folder +
                                        '",layer="' + filename + '")')
            elif isinstance(param, ParameterTable):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    value = param.value
                    if not value.lower().endswith('csv'):
                        raise GeoAlgorithmExecutionException(
                            'Unsupported input file format.\n' + value)
                    if self.passFileNames:
                        commands.append(param.name + ' = "' + value + '"')
                    else:
                        commands.append(param.name + ' <- read.csv("' + value +
                                        '", head=TRUE, sep=",")')
            elif isinstance(param, ParameterExtent):
                if param.value:
                    tokens = str(param.value).split(',')
                    # Extent from raster package is "xmin, xmax, ymin, ymax" like in Processing
                    # http://www.inside-r.org/packages/cran/raster/docs/Extent
                    commands.append(param.name + ' = extent(' + tokens[0] + ',' + tokens[1] + ',' + tokens[2] + ',' + tokens[3] + ')')
                else:
                    commands.append(param.name + ' = NULL')
            elif isinstance(param, ParameterCrs):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    commands.append(param.name + ' = "' + param.value + '"')
            elif isinstance(param, (ParameterTableField, ParameterString, ParameterFile)):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    commands.append(param.name + '="' + param.value + '"')
            elif isinstance(param, (ParameterNumber, ParameterSelection)):
                if param.value is None:
                    commands.append(param.name + '= NULL')
                else:
                    commands.append(param.name + '=' + str(param.value))
            elif isinstance(param, ParameterBoolean):
                if param.value:
                    commands.append(param.name + '=TRUE')
                else:
                    commands.append(param.name + '=FALSE')
            elif isinstance(param, ParameterMultipleInput):
                iLayer = 0
                if param.datatype == dataobjects.TYPE_RASTER:
                    layers = param.value.split(';')
                    for layer in layers:
                        layer = layer.replace('\\', '/')
                        if self.passFileNames:
                            commands.append('tempvar' + str(iLayer) + ' <- "' +
                                            layer + '"')
                        elif self.useRasterPackage:
                            commands.append('tempvar' + str(iLayer) + ' <- ' +
                                            'brick("' + layer + '")')
                        else:
                            commands.append('tempvar' + str(iLayer) + ' <- ' +
                                            'readGDAL("' + layer + '")')
                        iLayer += 1
                else:
                    exported = param.getSafeExportedLayers()
                    layers = exported.split(';')
                    for layer in layers:
                        if not layer.lower().endswith('shp') \
                           and not self.passFileNames:
                            raise GeoAlgorithmExecutionException(
                                'Unsupported input file format.\n' + layer)
                        layer = layer.replace('\\', '/')
                        filename = os.path.basename(layer)
                        filename = filename[:-4]
                        if self.passFileNames:
                            commands.append('tempvar' + str(iLayer) + ' <- "' +
                                            layer + '"')
                        else:
                            commands.append('tempvar' + str(iLayer) + ' <- ' +
                                            'readOGR("' + layer + '",layer="' +
                                            filename + '")')
                        iLayer += 1
                s = ''
                s += param.name
                s += ' = c('
                iLayer = 0
                for layer in layers:
                    if iLayer != 0:
                        s += ','
                    s += 'tempvar' + str(iLayer)
                    iLayer += 1
                s += ')\n'
                commands.append(s)

        if self.showPlots:
            htmlfilename = self.getOutputValue(RAlgorithm.RPLOTS)
            self.plotsFilename = htmlfilename + '.png'
            self.plotsFilename = self.plotsFilename.replace('\\', '/')
            commands.append('png("' + self.plotsFilename + '")')

        return commands

    def getRCommands(self):
        return self.commands

    def help(self):
        helpfile = str(self.descriptionFile) + '.help'
        if os.path.exists(helpfile):
            return True, getHtmlFromHelpFile(self, helpfile)
        else:
            return False, None

    def shortHelp(self):
        if self.descriptionFile is None:
            return None
        helpFile = str(self.descriptionFile) + '.help'
        if os.path.exists(helpFile):
            with open(helpFile) as f:
                try:
                    descriptions = json.load(f)
                    if 'ALG_DESC' in descriptions:
                        return self._formatHelp(str(descriptions['ALG_DESC']))
                except:
                    return None
        return None

    def getParameterDescriptions(self):
        descs = {}
        if self.descriptionFile is None:
            return descs
        helpFile = str(self.descriptionFile) + '.help'
        if os.path.exists(helpFile):
            with open(helpFile) as f:
                try:
                    descriptions = json.load(f)
                    for param in self.parameters:
                        if param.name in descriptions:
                            descs[param.name] = str(descriptions[param.name])
                except:
                    return descs
        return descs

    def checkBeforeOpeningParametersDialog(self):
        msg = RUtils.checkRIsInstalled()
        if msg is not None:
            html = self.tr(
                '<p>This algorithm requires R to be run. Unfortunately it '
                'seems that R is not installed in your system or it is not '
                'correctly configured to be used from QGIS</p>'
                '<p><a href="http://docs.qgis.org/testing/en/docs/user_manual/processing/3rdParty.html">Click here</a> '
                'to know more about how to install and configure R to be used with QGIS</p>')
            return html
