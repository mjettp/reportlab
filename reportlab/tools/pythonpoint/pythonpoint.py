#!/usr/bin/env python

"""
This is PythonPoint!

The idea is a simple markup languages for describing presentation
slides, and other documents which run page by page.  I expect most
of it will be reusable in other page layout stuff.

Look at the sample near the top, which shows how the presentation
should be coded up.

The parser, which is in a separate module to allow for multiple
parsers, turns the XML sample into an object tree.  There is a
simple class hierarchy of items, the inner levels of which create
flowable objects to go in the frames.  These know how to draw
themselves.

The currently available 'Presentation Objects' are:

    The main hierarchy...
        PPPresentation
        PPSection
        PPSlide
        PPFrame

        PPAuthor, PPTitle and PPSubject are optional
        
    Things to flow within frames...
        PPPara - flowing text
        PPPreformatted - text with line breaks and tabs, for code..
        PPImage
        PPTable - bulk formatted tabular data
        PPSpacer

    Things to draw directly on the page...
        PPRect
        PPRoundRect
        PPDrawingElement - user base class for graphics
        PPLine
        PPEllipse

Recently added features are:

- file globbing
- package structure
- named colors throughout (using names from reportlab/lib/colors.py)
- handout mode with arbitrary number of columns per page
- stripped off pages hidden in the outline tree (hackish)
- new <notes> tag for speaker notes (paragraphs only)
- new <pycode> tag for syntax-colorized Python code
- reformatted pythonpoint.xml and monterey.xml demos
- written/extended DTD
- arbitrary font support
- print proper speaker notes (TODO)
- fix bug with partially hidden graphics (TODO)
- save in combined presentation/handout mode (TODO)
- add pyRXP support (TODO)
"""

import os, sys, imp, string, pprint, getopt, glob

from reportlab import rl_config
from reportlab.lib import styles
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus.doctemplate import SimpleDocTemplate
from reportlab.platypus.flowables import Flowable
from reportlab.platypus.xpreformatted import PythonPreformatted 
from reportlab.platypus import Preformatted, Paragraph, Frame, \
     Image, Table, TableStyle, Spacer

import stdparser 


USAGE_MESSAGE = """\
PythonPoint - a tool for making presentations in PDF.

Usage:
    pythonpoint.py [options] file1.xml [file2.xml [...]]

    where options can be any of these:

        -h / --help     prints this message
        -n / --notes    leave room for comments
        -v / --verbose  verbose mode
        --handout       produce handout document
        --cols          specify number of columns
                        on handout pages (default: 2)

To create the PythonPoint user guide, do:
    pythonpoint.py pythonpoint.xml
"""


#####################################################################
# This should probably go into reportlab/lib/fonts.py...
#####################################################################

class FontNameNotFoundError(Exception):
    pass


class FontFilesNotFoundError(Exception):
    pass


##def findFontName(path):
##    "Extract a Type-1 font name from an AFM file."
##
##    f = open(path)
##
##    found = 0
##    while not found:
##        line = f.readline()[:-1]
##        if not found and line[:16] == 'StartCharMetrics':
##            raise FontNameNotFoundError, path
##        if line[:8] == 'FontName':
##            fontName = line[9:]
##            found = 1
##
##    return fontName
##
##
##def locateFilesForFontWithName(name):
##    "Search known paths for AFM/PFB files describing T1 font with given name."
##
##    join = os.path.join
##    splitext = os.path.splitext
##    
##    afmFile = None
##    pfbFile = None
##    
##    found = 0
##    while not found:
##        for p in rl_config.T1SearchPath:
##            afmFiles = glob.glob(join(p, '*.[aA][fF][mM]'))
##            for f in afmFiles:
##                T1name = findFontName(f)
##                if T1name == name:
##                    afmFile = f
##                    found = 1
##                    break
##            if afmFile:
##                break
##        break
##
##    if afmFile:
##        pfbFile = glob.glob(join(splitext(afmFile)[0] + '.[pP][fF][bB]'))[0]
##
##    return afmFile, pfbFile
##
##    
##def registerFont(name):
##    "Register Type-1 font for future use."
##
##    rl_config.warnOnMissingFontGlyphs = 0
##    rl_config.T1SearchPath.append(r'C:\Programme\Python21\reportlab\test')
##
##    afmFile, pfbFile = locateFilesForFontWithName(name)
##    if not afmFile and not pfbFile:
##        raise FontFilesNotFoundError
##
##    T1face = pdfmetrics.EmbeddedType1Face(afmFile, pfbFile)
##    T1faceName = name
##    pdfmetrics.registerTypeFace(T1face)
##    T1font = pdfmetrics.Font(name, T1faceName, 'WinAnsiEncoding')
##    pdfmetrics.registerFont(T1font)


def registerFont0(sourceFile, name, path):
    "Register Type-1 font for future use, simple version."

    rl_config.warnOnMissingFontGlyphs = 0

    p = os.path.join(os.path.dirname(sourceFile), path)
    afmFiles = glob.glob(p + '.[aA][fF][mM]')
    pfbFiles = glob.glob(p + '.[pP][fF][bB]')
    assert len(afmFiles) == len(pfbFiles) == 1, FontFilesNotFoundError                         

    T1face = pdfmetrics.EmbeddedType1Face(afmFiles[0], pfbFiles[0])
    T1faceName = name
    pdfmetrics.registerTypeFace(T1face)
    T1font = pdfmetrics.Font(name, T1faceName, 'WinAnsiEncoding')
    pdfmetrics.registerFont(T1font)

#####################################################################


def checkColor(col):
    "Converts a color name to an RGB tuple, if possible."

    if type(col) == type('') and col in dir(colors):
        col = getattr(colors, col)
        col = (col.red, col.green, col.blue)

    return col


def handleHiddenSlides(slides):
    """Filters slides from a list of slides.
    
    In a sequence of hidden slides all but the last one are
    removed. Also, the slide before the sequence of hidden
    ones is removed.

    This assumes to leave only those slides in the handout
    that also appear in the outline, hoping to reduce se-
    quences where each new slide only adds one new line
    to a list of items...
    """

    itd = indicesToDelete = map(lambda s:s.outlineEntry == None, slides)

    for i in range(len(itd)-1):
        if itd[i] == 1:
            if itd[i+1] == 0:
                itd[i] = 0
            if i > 0 and itd[i-1] == 0:
                itd[i-1] = 1
    
    for i in range(len(itd)):
        if itd[i] == 1:
            slides[i].delete = 1
        else:
            slides[i].delete = 0

    slides = filter(lambda s:s.delete == 0, slides)

    return slides


def makeSlideTable(slides, pageSize, docWidth, numCols):
    """Returns a table containing a collection of SlideWrapper flowables.
    """

    slides = handleHiddenSlides(slides)
    
    # Set table style.
    tabStyle = TableStyle(
        [('GRID', (0,0), (-1,-1), 0.25, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTRE')
         ])

    # Build table content.
    width = docWidth/numCols
    height = width * pageSize[1]/pageSize[0]
    matrix = []
    row = []
    for slide in slides:
        sw = SlideWrapper(width, height, slide, pageSize)
        if (len(row)) < numCols:
            row.append(sw)
        else:
            matrix.append(row)
            row = []
            row.append(sw)
    if len(row) > 0:
        for i in range(numCols-len(row)):
            row.append('')
        matrix.append(row)

    # Make Table flowable.
    t = Table(matrix,
              [width + 5]*len(matrix[0]),
              [height + 5]*len(matrix))
    t.setStyle(tabStyle)

    return t


class SlideWrapper(Flowable):
    """A Flowable wrapping a PPSlide object.
    """

    def __init__(self, width, height, slide, pageSize):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.slide = slide
        self.pageSize = pageSize


    def __repr__(self):
        return "SlideWrapper(w=%s, h=%s)" % (self.width, self.height)


    def draw(self):
        "Draw the slide in our relative coordinate system."

        slide = self.slide
        pageSize = self.pageSize
        canv = self.canv

        canv.saveState()
        canv.scale(self.width/pageSize[0], self.height/pageSize[1])
        slide.effectName = None
        slide.drawOn(self.canv)
        canv.restoreState()


class PPPresentation:
    def __init__(self):
        self.sourceFilename = None
        self.filename = None
        self.description = None
        self.title = None
        self.author = None
        self.subject = None
        self.notes = 0          # different printing mode
        self.handout = 0        # prints many slides per page
        self.cols = 0           # columns per handout page
        self.slides = []
        self.effectName = None
        self.showOutline = 1   #should it be displayed when opening?
        self.compression = 1        
        #assume landscape
        self.pageWidth = rl_config.defaultPageSize[1]  
        self.pageHeight = rl_config.defaultPageSize[0]  


    def saveAsPresentation(self):
        """Write the PDF document, one slide per page."""

        pageSize = (self.pageWidth, self.pageHeight)
        filename = os.path.splitext(self.sourceFilename)[0] + '.pdf'
        canv = canvas.Canvas(filename, pagesize = pageSize)
        canv.setPageCompression(self.compression)

        if self.title:
            canv.setTitle(self.title)
        if self.author:
            canv.setAuthor(self.author)
        if self.subject:
            canv.setSubject(self.subject)

        for slide in self.slides:
            if self.notes:
                #frame and shift the slide
                canv.scale(0.67, 0.67)
                canv.translate(self.pageWidth / 6.0, self.pageHeight / 3.0)
                canv.rect(0,0,self.pageWidth, self.pageHeight)
            slide.drawOn(canv)
            canv.showPage()

        #ensure outline visible by default
        if self.showOutline:
            canv.showOutline()

        canv.save()        


    def saveAsHandout(self):
        """Write the PDF document, multiple slides per page."""

        styleSheet = getSampleStyleSheet()
        h1 = styleSheet['Heading1']
        bt = styleSheet['BodyText']

        filename = os.path.splitext(self.sourceFilename)[0] + '.pdf'
        doc = SimpleDocTemplate(filename, pagesize=rl_config.defaultPageSize, showBoundary=0)

        doc.leftMargin = 1*cm
        doc.rightMargin = 1*cm
        doc.topMargin = 2*cm
        doc.bottomMargin = 2*cm
        multiPageWidth = rl_config.defaultPageSize[0] - doc.leftMargin - doc.rightMargin - 50
        
        story = []
        orgFullPageSize = (self.pageWidth, self.pageHeight)
        t = makeSlideTable(self.slides, orgFullPageSize, multiPageWidth, self.cols)
        story.append(t)

##        #ensure outline visible by default
##        if self.showOutline:
##            doc.canv.showOutline()

        doc.build(story)

    
    def save(self):
        "Save the PDF document."
        
        if self.handout:
            self.saveAsHandout()
        else:
            self.saveAsPresentation()


class PPSection:
    """A section can hold graphics which will be drawn on all
    pages within it, before frames and other content are done.
    In other words, a background template."""

    def __init__(self, name):
        self.name = name
        self.graphics = []
        
    def drawOn(self, canv):
        for graphic in self.graphics:
##            graphic.drawOn(canv)

            name = str(hash(graphic))
            internalname = canv._doc.hasForm(name)

            canv.saveState()
            if not internalname:
                canv.beginForm(name)
                graphic.drawOn(canv)
                canv.endForm()
                canv.doForm(name)
            else:
                canv.doForm(name)
            canv.restoreState()
            

class PPNotes:
    def __init__(self):
        self.content = []
    
    def drawOn(self, canv):
        print self.content
    

class PPSlide:
    def __init__(self):
        self.id = None
        self.title = None
        self.outlineEntry = None
        self.outlineLevel = 0   # can be higher for sub-headings
        self.effectName = None
        self.effectDirection = 0
        self.effectDimension = 'H'
        self.effectMotion = 'I'
        self.effectDuration = 1
        self.frames = []
        self.notes = []
        self.graphics = []
        self.section = None

    def drawOn(self, canv):
        if self.effectName:
            canv.setPageTransition(
                        effectname=self.effectName,
                        direction = self.effectDirection,
                        dimension = self.effectDimension,
                        motion = self.effectMotion,
                        duration = self.effectDuration
                        )

        if self.outlineEntry:
            #gets an outline automatically
            self.showOutline = 1
            #put an outline entry in the left pane
            tag = self.title
            canv.bookmarkPage(tag)
            canv.addOutlineEntry(tag, tag, self.outlineLevel)
            
        if self.section:
            self.section.drawOn(canv)
                
        for graphic in self.graphics:
            graphic.drawOn(canv)
            
        for frame in self.frames:
            frame.drawOn(canv)

##        # Need to draw the notes *somewhere*...
##        for note in self.notes:
##            print note


class PPFrame:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.content = []
        self.showBoundary = 0        

    def drawOn(self, canv):
        #make a frame
        frame = Frame( self.x,
                              self.y,
                              self.width,
                              self.height
                              )
        frame.showBoundary = self.showBoundary
 
        #build a story for the frame
        story = []
        for thingy in self.content:
            #ask it for any flowables
            story.append(thingy.getFlowable())
        #draw it
        frame.addFromList(story,canv)

 
class PPPara:
    """This is a placeholder for a paragraph."""
    def __init__(self):
        self.rawtext = ''
        self.style = None

    def getFlowable(self):
        p = Paragraph(
                    self.rawtext,
                    getStyles()[self.style],
                    self.bulletText
                    )
        return p


class PPPreformattedText:
    """Use this for source code, or stuff you do not want to wrap"""
    def __init__(self):
        self.rawtext = ''
        self.style = None

    def getFlowable(self):
        return Preformatted(self.rawtext, getStyles()[self.style])


class PPPythonCode:
    """Use this for colored Python source code"""
    def __init__(self):
        self.rawtext = ''
        self.style = None

    def getFlowable(self):
        return PythonPreformatted(self.rawtext, getStyles()[self.style])


class PPImage:
    """Flowing image within the text"""
    def __init__(self):
        self.filename = None
        self.width = None
        self.height = None

    def getFlowable(self):
        return Image(self.filename, self.width, self.height)


class PPTable:
    """Designed for bulk loading of data for use in presentations."""
    def __init__(self):
        self.rawBlocks = [] #parser stuffs things in here...
        self.fieldDelim = ','  #tag args can override
        self.rowDelim = '\n'   #tag args can override
        self.data = None
        self.style = None  #tag args must specify
        self.widths = None  #tag args can override
        self.heights = None #tag args can override

    def getFlowable(self):
        self.parseData()
        t = Table(
				self.data,
                self.widths,
                self.heights)
        if self.style:
            t.setStyle(getStyles()[self.style])

        return t
                
    def parseData(self):
        """Try to make sense of the table data!"""
        rawdata = string.strip(string.join(self.rawBlocks, ''))
        lines = string.split(rawdata, self.rowDelim)
        #clean up...
        lines = map(string.strip, lines)
        self.data = []
        for line in lines:
            cells = string.split(line, self.fieldDelim)
            self.data.append(cells)

        #get the width list if not given
        if not self.widths:
            self.widths = [None] * len(self.data[0])
        if not self.heights:
            self.heights = [None] * len(self.data)
        
##        import pprint
##        print 'table data:'
##        print 'style=',self.style
##        print 'widths=',self.widths
##        print 'heights=',self.heights
##        print 'fieldDelim=',repr(self.fieldDelim)
##        print 'rowDelim=',repr(self.rowDelim)
##        pprint.pprint(self.data)


class PPSpacer:
    def __init__(self):
        self.height = 24  #points

    def getFlowable(self):
        return Spacer(72, self.height)


    #############################################################
    #
    #   The following are things you can draw on a page directly.
    #
    ##############################################################

##class PPDrawingElement:
##    """Base class for something which you draw directly on the page."""
##    def drawOn(self, canv):
##        raise "NotImplementedError", "Abstract base class!"

        
class PPFixedImage:
    """You place this on the page, rather than flowing it"""
    def __init__(self):
        self.filename = None
        self.x = 0
        self.y = 0
        self.width = None
        self.height = None

    def drawOn(self, canv):
        if self.filename:
            x, y = self.x, self.y
            w, h = self.width, self.height
            canv.drawInlineImage(self.filename, x, y, w, h)


class PPRectangle:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.fillColor = None
        self.strokeColor = (1,1,1)
        self.lineWidth=0

    def drawOn(self, canv):
        canv.saveState()
        canv.setLineWidth(self.lineWidth)
        if self.fillColor:
            r,g,b = checkColor(self.fillColor)
            canv.setFillColorRGB(r,g,b)
        if self.strokeColor:
            r,g,b = checkColor(self.strokeColor)
            canv.setStrokeColorRGB(r,g,b)
        canv.rect(self.x, self.y, self.width, self.height,
                    stroke=(self.strokeColor<>None),
                    fill = (self.fillColor<>None)
                    )
        canv.restoreState()
                                   

class PPRoundRect:
    def __init__(self, x, y, width, height, radius):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.radius = radius
        self.fillColor = None
        self.strokeColor = (1,1,1)
        self.lineWidth=0
        
    def drawOn(self, canv):
        canv.saveState()
        canv.setLineWidth(self.lineWidth)
        if self.fillColor:
            r,g,b = checkColor(self.fillColor)
            canv.setFillColorRGB(r,g,b)
        if self.strokeColor:
            r,g,b = checkColor(self.strokeColor)
            canv.setStrokeColorRGB(r,g,b)
        canv.roundRect(self.x, self.y, self.width, self.height,
                    self.radius,
                    stroke=(self.strokeColor<>None),
                    fill = (self.fillColor<>None)
                    )
        canv.restoreState()


class PPLine:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.fillColor = None
        self.strokeColor = (1,1,1)
        self.lineWidth=0
        
    def drawOn(self, canv):
        canv.saveState()
        canv.setLineWidth(self.lineWidth)
        if self.strokeColor:
            r,g,b = checkColor(self.strokeColor)
            canv.setStrokeColorRGB(r,g,b)
        canv.line(self.x1, self.y1, self.x2, self.y2)
        canv.restoreState()


class PPEllipse:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.fillColor = None
        self.strokeColor = (1,1,1)
        self.lineWidth=0
        
    def drawOn(self, canv):
        canv.saveState()
        canv.setLineWidth(self.lineWidth)
        if self.strokeColor:
            r,g,b = checkColor(self.strokeColor)
            canv.setStrokeColorRGB(r,g,b)
        if self.fillColor:
            r,g,b = checkColor(self.fillColor)
            canv.setFillColorRGB(r,g,b)
        canv.ellipse(self.x1, self.y1, self.x2, self.y2,
                    stroke=(self.strokeColor<>None),
                    fill = (self.fillColor<>None)
                     )
        canv.restoreState()


class PPPolygon:
    def __init__(self, pointlist):
        self.points = pointlist
        self.fillColor = None
        self.strokeColor = (1,1,1)
        self.lineWidth=0
        
    def drawOn(self, canv):
        canv.saveState()
        canv.setLineWidth(self.lineWidth)
        if self.strokeColor:
            r,g,b = checkColor(self.strokeColor)
            canv.setStrokeColorRGB(r,g,b)

        path = canv.beginPath()
        (x,y) = self.points[0]
        path.moveTo(x,y)
        for (x,y) in self.points[1:]:
            path.lineTo(x,y)
        path.close()
        canv.drawPath(path, stroke=(self.strokeColor<>None))
        canv.restoreState()

    
class PPString:
    def __init__(self, x, y):
        self.text = ''
        self.x = x
        self.y = y
        self.align = TA_LEFT
        self.font = 'Times-Roman'
        self.size = 12
        self.color = (0,0,0)
        self.hasInfo = 0  # these can have data substituted into them

    def normalizeText(self):
        """It contains literal XML text typed over several lines.
        We want to throw away
        tabs, newlines and so on, and only accept embedded string
        like '\n'"""
        lines = string.split(self.text, '\n')
        newtext = []
        for line in lines:
            newtext.append(string.strip(line))
        #accept all the '\n' as newlines
            
        self.text = newtext
        
    def drawOn(self, canv):
        # for a string in a section, this will be drawn several times;
        # so any substitution into the text should be in a temporary
        # variable
        if self.hasInfo:
            # provide a dictionary of stuff which might go into
            # the string, so they can number pages, do headers
            # etc.
            info = {}
            info['title'] = canv._doc.info.title
            info['author'] = canv._doc.info.author
            info['subject'] = canv._doc.info.subject
            info['page'] = canv.getPageNumber()
            drawText = self.text % info
        else:
            drawText = self.text

        if self.color is None:
            return
        lines = string.split(string.strip(drawText), '\\n')
        canv.saveState()

        canv.setFont(self.font, self.size)

        r,g,b = checkColor(self.color)
        canv.setFillColorRGB(r,g,b)
        cur_y = self.y
        for line in lines:
            if self.align == TA_LEFT:
                canv.drawString(self.x, cur_y, line)
            elif self.align == TA_CENTER:
                canv.drawCentredString(self.x, cur_y, line)
            elif self.align == TA_RIGHT:
                canv.drawRightString(self.x, cur_y, line)
            cur_y = cur_y - 1.2*self.size
                
        canv.restoreState()


def getSampleStyleSheet():
    from styles.standard import getParagraphStyles
    return getParagraphStyles()


#make a singleton and a function to access it        
_styles = None
def getStyles():
    global _styles
    if not _styles:
        _styles = getSampleStyleSheet()
    return _styles


def setStyles(newStyleSheet):
    global _styles
    _styles = newStyleSheet

        
##def test():
##    p = stdparser.PPMLParser()
##    p.feed(sample)
##    p.getPresentation().save()
##    p.close()


def process(datafilename, notes=0, handout=0, cols=0):
    "Process one PythonPoint source file."
    
    parser = stdparser.PPMLParser()
    parser.sourceFilename = datafilename
    rawdata = open(datafilename).read()
    parser.feed(rawdata)
    pres = parser.getPresentation()
    pres.sourceFilename = datafilename
    pres.notes = notes
    pres.handout = handout
    pres.cols = cols
    pres.save()
    if rl_config._verbose:
        print 'saved presentation %s.pdf' % os.path.splitext(datafilename)[0]
    parser.close()


##class P:
##    def feed(self, text):
##        parser = stdparser.PPMLParser()
##        d = pyRXP.parse(text)
##    
##
##def process2(datafilename, notes=0, handout=0, cols=0):
##    "Process one PythonPoint source file."
##    
##    import pyRXP, pprint
##
##    rawdata = open(datafilename).read()
##    d = pyRXP.parse(rawdata)
##    pprint.pprint(d)


def handleOptions():
    # set defaults
    options = {'cols':2,
               'handout':0,
               'help':0,
               'notes':0,
               'verbose':0}

    try:
        shortOpts = 'hnv'
        longOpts = string.split('cols= handout help notes verbose', ' ')
        optList, args = getopt.getopt(sys.argv[1:], shortOpts, longOpts)
    except getopt.error, msg:
        options['help'] = 1

    if not args and os.path.isfile('pythonpoint.xml'):
        args = ['pythonpoint.xml']

    # Remove leading dashes (max. two).
    for i in range(len(optList)):
        o, v = optList[i]
        while o[0] == '-':
            o = o[1:]
        optList[i] = (o, v)

        if o == 'cols':
            options['cols'] = int(v)

    if filter(lambda ov: ov[0] == 'handout', optList):
        options['handout'] = 1

    if optList == [] and args == [] or \
       filter(lambda ov: ov[0] in ('h', 'help'), optList):
        options['help'] = 1
        
    if filter(lambda ov: ov[0] in ('n', 'notes'), optList):
        options['notes'] = 1

    if filter(lambda ov: ov[0] in ('v', 'verbose'), optList):
        options['verbose'] = 1

    return options, args


if __name__ == '__main__':
    options, args = handleOptions()

    if options['help']:
        print USAGE_MESSAGE
        sys.exit(0)

    if options['verbose'] and options['notes']:
        print 'speaker notes mode'

    if options['verbose'] and options['handout']:
        print 'handout mode'

    for fileGlobs in args:
        files = glob.glob(fileGlobs)
        for datafile in files:
            if os.path.isfile(datafile):
                file = os.path.join(os.getcwd(), datafile)
                notes, handout, cols = options['notes'], options['handout'], options['cols']
                process(file, notes, handout, cols)
            else:
                print 'Data file not found:', datafile