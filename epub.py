#!/usr/bin/env python2
##
## epub reading and writing
##
import re,sys, traceback, zipfile, os
import os.path
import xml.dom.minidom
from xml.dom.minidom import Node, DOMImplementation



class ReadEPUB:
    def __init__(self, fname,log,lang):
        self.fname = fname
        self.lang = lang
        self.zfile = zipfile.ZipFile(fname,'r',zipfile.ZIP_DEFLATED,True)
        log('opened', fname)

        ## opf to use
        opf_file = self.xget( self.xml('META-INF/container.xml'), ['<container','<rootfiles','<rootfile'],'full-path')
        log('opf is',opf_file)

        opf_dir = os.path.dirname(opf_file)

        ## toc item
        toc_item = self.xget(self.xml(opf_file),['<package','<spine'],'toc')
        log('toc item is',toc_item)

        ## toc file
        if toc_item:
            toc_file = self.xget(self.xml(opf_file),['<package','<manifest','<item', '#'+toc_item],'href')
            log('toc file is' , toc_file)
        else:
            log('No TOC','')
            toc_file = None

        ## nav file
        nav_file = self.xget(self.xml(opf_file),['<package','<manifest','<item', '=properties=nav'],'href')
        log('nav file is' , nav_file)

        ## content items
        txt_items = self.xgetall(self.xml(opf_file),['<package','<spine','<itemref'],"idref")
        log('txt items is',*txt_items)

        ## content files
        txt_files = [ self.xget(self.xml(opf_file),['<package','<manifest','<item', '#'+i],'href') for i in txt_items]
        log('txt files is',*txt_files)


        self.content = {}
        self.curpage = 0
        self.pages = []
        ### Taking the order of files from OPF ( rather than from NAV )
        for tf in txt_files:
            if tf == nav_file:
                continue
            rf = os.path.relpath(tf, os.path.dirname(nav_file))
            log("Processing " , tf, "( ", rf ,')' )
            with self.zfile.open(opf_dir + "/" + tf) as fd:
                orig = fd.read()
                modi = re.sub(r'~!~([\sa-zA-z0-9_+-]*)~@~', lambda x: self.to_pagenumber(rf,x) , orig)
                if orig != modi :
                    self.content[opf_dir + "/" + tf] = modi
        ### Now update the nav.
        navdom = self.xml(opf_dir + "/" + nav_file)
        ## <nav epub:type="page-list">
        ele_nav = navdom.createElement('nav')
        navdom.getElementsByTagName('html')[0].getElementsByTagName('body')[0].appendChild(ele_nav)
        ele_nav.setAttribute('epub:type','page-list')
        ## h1
        ele_h1 = navdom.createElement('h1')
        ele_nav.appendChild(ele_h1)
        ele_h1.appendChild(navdom.createTextNode('Ink Print Page List'))
        ## ol
        ele_ol = navdom.createElement('ol')
        ele_nav.appendChild(ele_ol)
        ## li a href =
        for lp in self.pages:
            ele_li = navdom.createElement('li')
            ele_ol.appendChild(ele_li)
            ele_a = navdom.createElement('a')
            ele_li.appendChild(ele_a)
            ele_a.setAttribute('href',lp[0])
            ele_a.appendChild(navdom.createTextNode(lp[1]))

        ## make sure nav_file is proper html.
        doctype = DOMImplementation().createDocumentType( qualifiedName='html', publicId='', systemId='' )
        navdom.insertBefore(doctype,navdom.documentElement)
        html = navdom.documentElement
        html.setAttribute('xmlns',"http://www.w3.org/1999/xhtml")
        html.setAttribute('xmlns:epub',"http://www.idpf.org/2007/ops")
        html.setAttribute('xml:lang',self.lang)
        html.setAttribute('lang',self.lang)
        self.content[opf_dir + "/" + nav_file] = navdom.toprettyxml(encoding='utf-8')


        ##
        #print(opf_file)
        #self.pxml(self.xml(opf_file))
        #print(opf_dir + "/" + toc_file)
        #self.pxml(self.xml(opf_dir + "/" + toc_file))
        #print(opf_dir + "/" + nav_file)
        #self.pxml(self.xml(opf_dir + "/" + nav_file))
        ##

    def has_data(self):
        return not not self.pages

    def to_pagenumber(self,relname, match):
        pn = match.group(1).strip()
        if not pn or pn == '+':
            self.curpage = self.curpage + 1
            pn = str(self.curpage)
        else:
            try:
                self.curpage = int(pn)
            except :
                self.curpage = 999999
        ## pn is the page number .. fix the id
        id = pn
        while len(id) < 4:
            id = '0' + id
        id = id.replace(' ','-')
        ## things..
        lnk = "%s#page%s" % ( relname, id)
        self.pages.append([ lnk,pn])
        log( "    Page ", pn, " at ", lnk)
        return '<span epub:type="pagebreak" id="page%s">%s</span>' % (id,pn)


    def xml(self,fname):
        with self.zfile.open(fname) as fd:
            return xml.dom.minidom.parse(fd)

    def xget(self,dom,path,attr):
        eles = self.xpath(dom,path)
        assert len(eles) == 1
        return eles[0].getAttribute(attr)

    def xgetall(self,dom,path,attr):
        eles = self.xpath(dom,path)
        return [  e.getAttribute(attr) for e in eles ]

    ## path is array of
    #    <tag
    #    #id
    #    =attr=val
    # returns multiple values
    def xpath(self,dom,path):
        ret = [dom]
        for p in path :
            tmp = []
            for d in ret:
                if p[0] == '<':  ## tag
                    tmp.extend(d.getElementsByTagName(p[1:]))
                elif p[0] == '#': ## id=
                    if d.getAttribute('id') == p[1:]:
                        tmp.append(d)
                elif p[0] == '=' : ## attr=value
                    a_v = p[1:].split('=')
                    if d.getAttribute(a_v[0]) == a_v[1]:
                        tmp.append(d)
                else:
                    print "****Unrecognized path element " ,p
            ret = tmp
        return ret



    def pxml(self,dom):
        print(dom.toprettyxml(encoding='utf-8'))


    def copy_to(self, newfile):
        with zipfile.ZipFile(newfile,'w',zipfile.ZIP_DEFLATED,True) as outzip:
            for info in self.zfile.infolist():
                txt = self.content[info.filename]  if info.filename in self.content else self.zfile.read(info)
                outzip.writestr(info, txt ,zipfile.ZIP_DEFLATED)



def add_pagebreak( input_dir ,
                   output_dir ,
                   logfn,
                   lang ):
    ## Recurse in input_Dir
    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)
    for path, dir, files in os.walk(input_dir):
        for f in files:
            if not f.lower().endswith(".epub"):
                log("Ignoring ( not .epub ): ", f)
                continue
            try:
                relname = os.path.relpath(path,input_dir)
                in_file = os.path.join(input_dir,relname,f)
                out_file = os.path.join(output_dir,relname,f)
                logfn("***\nConverting ", in_file, " to ", out_file)
                p = ReadEPUB(in_file,logfn,lang)
                if p.has_data():
                    if not os.path.exists(os.path.dirname(out_file)):
                        os.makedirs(os.path.dirname(out_file))
                    p.copy_to(out_file)
                    logfn("WROTE: ",out_file)

                else:
                    logfn("SKIP: No page markers found")
            except:
                logfn("**********************************************************")
                logfn(" AN INTERNAL ERROR HAS OCCURED ")
                logfn(" Please send content of this buffer to fix this issue")
                logfn(" Visit http://github.com/vrdhn/epub-page-break to submit issue")
                logfn(" Or email author at vrdhn0@gmail.com with this file")
                logfn("**********************************************************")
                logfn(traceback.format_exc())
                logfn("**********************************************************")
            logfn('And we are done with this ...')

    return True




if __name__ == "__main__":
    def log(*args):
        print ' '.join([str(y) for y in args])
    if len(sys.argv) != 3 and len(sys.argv) != 4 :
        print "Usage: ./epub_-page_break.py <input_dir> <output_dir> [lang: en, hi etc.]"
    else:
        lang = sys.argv[3] if len(sys.argv)  == 4 else 'en'
        add_pagebreak(input_dir = sys.argv[1], output_dir = sys.argv[2], logfn = log, lang = lang)
