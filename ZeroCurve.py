from copy import deepcopy
import math
import numpy as np
import QuantLib as ql
class ZeroCurve(object):
    """Zero Rate Curve, Dates are all stored as Serial number"""
    def __init__(self,
                 name,
                 valuationdate,  #valuation date as int
                 tenors,    #tenors as string
                 tenordates,
                 zerorates):  
        self.name=name
        self.valuationdate=valuationdate
        self.tenors=tenors
        self.tenordates=tenordates
        self.zerorates=zerorates
        self.observerindex=[]
        self.derivedcurves=[]

    #def getDiscount(self,date):
    #    r=getZeroRate(date)
    #    return exp(-r*(date-self.valuationdate)/365.0)

    #def getZeroRate(self,date): #Linear interpolation on rates
    #    return np.interp(date,self.tenordates, self.zerorates)  

    def getallzeros(self):
        return self.zerorates

    def getQLZeroCurve(self):
        dates=self.tenordates
        zeros=self.zerorates
        dates1=[ql.Date(i.serialNumber()) for i in dates]
        zeros1=deepcopy(zeros)
        dates1.insert(0,self.valuationdate)
        zeros1.insert(0,self.zerorates[0])
        calendar=ql.WeekendsOnly()
        dates1.append(calendar.advance(dates1[-1],1,ql.Years))
        zeros1.append(zeros1[-1])
        return ql.ZeroCurve(dates1,zeros1,
                            ql.Actual365Fixed(),ql.UnitedStates(),
                            ql.Linear(),ql.Continuous)
    def updateZeroRates(self,zeros):
        self.zerorates=zeros
        self.QLZeroCurve.linkTo(self.getQLZeroCurve())
        for item in self.derivedcurves:
            item.updatebybasecurve()
    
    def initializeQLZeroCurve(self):
            self.QLZeroCurve=ql.RelinkableYieldTermStructureHandle(self.getQLZeroCurve())

    def getalltenors(self):
        return self.tenordates

    def getdata(self):
        return self.tenors, self.zerorates

    def register(self, i):  #register instrument index to the curve      
        self.observerindex.append(i)

    def registerderivedcurve(self,derivedcurve):  #for spread curves
        self.derivedcurves.append(derivedcurve)

    def updatedependency(self,curveset):
        pass
    
    def consolidateinstrument(self):
        for curve in self.derivedcurves:
            self.observerindex+=curve.observerindex
        self.observerindex=list(set(self.observerindex))


class ZeroSpreadCurve(object):
    def __init__(self,name,
                 basecurve,                
                 valuationdate,  #valuation date as int
                 tenors,    #tenors as string
                 tenordates,
                 zerospreads,
                 nullbeforefirstpillar=False):
        self.name=name
        self.zerorates=zerospreads
        self.tenors=tenors
        self.valuationdate=valuationdate
        self.tenordates=tenordates
        self.basecurvename=basecurve  #base curve name, not the handle
        self.observerindex=[]
        self.QLZeroCurve=None
        self.nullbeforefirstpillar=nullbeforefirstpillar

    def getQLZeroCurve(self):
        #dates1=[ql.Date(i.serialNumber()) for i in dates]
        #zeros1=deepcopy(zeros)
        x1=[i.serialNumber() for i in self.tenordates]
        y1=self.zerorates
        x2=[i.serialNumber() for i in self.basecurve.tenordates]
        y2=self.basecurve.zerorates
        datesS=x1+list(set(x2)-set(x1))
        datesS.sort()
        dates1=[]
        for i in range(0,len(datesS)):
            dates1.append(ql.Date(datesS[i]))
        if self.nullbeforefirstpillar:
            zeros1=np.interp(datesS,x1,y1,left=0.0,right=y1[-1])\
                +np.interp(datesS,x2,y2,left=y2[0],right=y2[-1])
        else:
            zeros1=np.interp(datesS,x1,y1,left=y1[0],right=y1[-1])\
                 +np.interp(datesS,x2,y2,left=y2[0],right=y2[-1])
        dates1.insert(0,self.valuationdate)
        zeros1=zeros1.tolist()
        zeros1.insert(0,zeros1[0])
        calendar=ql.WeekendsOnly()
        dates1.append(calendar.advance(dates1[-1],1,ql.Years))
        zeros1.append(zeros1[-1])
        return ql.ZeroCurve(dates1,zeros1,
                            ql.Actual365Fixed(),ql.UnitedStates(),
                            ql.Linear(),ql.Continuous)
    
    def updatebybasecurve(self):
        self.QLZeroCurve.linkTo(self.getQLZeroCurve())
        
    def updateZeroRates(self,zerospreads):
        self.zerorates=zerospreads
        self.QLZeroCurve.linkTo(self.getQLZeroCurve())
    
    def register(self, i):  #register the index for the instrument
        self.observerindex.append(i)


    def updatedependency(self,curveset):
        curveset[self.basecurvename].registerderivedcurve(self)
        self.basecurve=curveset[self.basecurvename]     
    
    def initializeQLZeroCurve(self):
            self.QLZeroCurve=ql.RelinkableYieldTermStructureHandle(self.getQLZeroCurve())

    def consolidateinstrument(self):
        self.observerindex=list(set(self.observerindex))


