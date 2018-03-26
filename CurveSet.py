import CurveSet.ZeroCurve as zc
import numpy as np
import scipy as sp
import QuantLib as ql
import xlwings as xw
import pandas as pd
from copy import deepcopy
from scipy.optimize import least_squares
from abc import ABC, abstractclassmethod
from numpy.linalg import inv
from collections import OrderedDict

class instrument(ABC):   #bootstrapping instrument details, construction and pricing of 
    '''bootstrapping instrument: this class contains details of the instrment, '''
    '''construction and pricing of intrument are done in curve bootstrapping class'''
    '''because the the curves assignment and schedules need to be updated there'''
    def __init__(self,
                 valuationdate,
                 quote,
                 type):
        self.valuationdate=valuationdate
        self.quote=quote
        self.type=type
        super().__init__()

    @abstractclassmethod
    def impliedquote(self):
        pass
    @abstractclassmethod
    def registerindex(self, index):    #assign index to the instrument, so that Jacobian can be calculated 
        pass
    @abstractclassmethod
    def assigncurves(self, curves):
        pass

class DEPO(instrument):
    def __init__(self,
                 valuationdate, 
                 quote,
                 tenor,
                 settledays,
                 daycount,
                 calendar,
                 discurve,
                 businessday_convention=ql.ModifiedFollowing):
        super().__init__(valuationdate,quote,'DEPO')
        self.tenor=tenor
        self.daycount=daycount
        self.calendar=calendar
        self.businessday_convention=businessday_convention
        #self.settledays=settledays
        self.discurve=discurve   #discount curve name
        if tenor=='ON':
            self.startdate=valuationdate
            self.enddate=self.calendar.advance(valuationdate,1,ql.Days)
        elif tenor=='TN':
            self.startdate=self.calendar.advance(valuationdate,1,ql.Days)
            self.enddate=self.calendar.advance(self.startdate,1,ql.Days)
        elif tenor=='SN':
            self.startdate=self.calendar.advance(valuationdate,int(settledays),ql.Days)
            self.enddate=self.calendar.advance(self.startdate,1,ql.Days)
        else:
            period=ql.Period(int(settledays),ql.Days)
            self.startdate=self.calendar.advance(valuationdate,period)
            period=ql.Period(tenor)
            self.enddate=self.calendar.advance(self.startdate,period)

    def impliedquote(self):
        yearfrac=self.daycount.yearFraction(self.startdate,self.enddate)
        impliedquote=(self.curve.QLZeroCurve.discount(self.startdate) \
                    /self.curve.QLZeroCurve.discount(self.enddate)-1)/yearfrac
        return impliedquote
    def registerindex(self,index):
        self.index=index

    def assigncurves(self, curves):
        self.curve=curves[self.discurve]
        self.curve.register(self.index)


class FRA(instrument):
    def __init__(self,
                 valuationdate,
                 quote,
                 settledays,
                 startmonth,
                 endmonth,
                 daycount,
                 calendar,
                 discurve,
                 businessday_convention=ql.ModifiedFollowing):
        super().__init__(valuationdate,quote,'FRA')
        self.daycount=daycount
        self.calendar=calendar
        self.discurve=discurve   #discount curve name
        period=ql.Period(int(settledays),ql.Days)
        spotdate=self.calendar.advance(valuationdate,period)
        period=ql.Period((startmonth),ql.Months)
        self.startdate=self.calendar.advance(spotdate,period,True)
        period=ql.Period((endmonth-startmonth),ql.Months)
        self.enddate=self.calendar.advance(self.startdate,period,businessday_convention,True)
    def impliedquote(self):
        yearfrac=self.daycount.yearFraction(self.startdate,self.enddate)
        impliedquote=(self.curve.QLZeroCurve.discount(self.startdate) \
                    /self.curve.QLZeroCurve.discount(self.enddate)-1)/yearfrac
        return impliedquote

    def registerindex(self,index):
        self.index=index

    def assigncurves(self, curves):
        self.curve=curves[self.discurve]
        self.curve.register(self.index)
        

class Futures(instrument):
    def __init__(self,
                 valuationdate,
                 quote,
                 settledays,
                 length,
                 calendar,
                 daycount,
                 discurve,
                 futureindex,
                 futuretype='IMM',
                 bussinessday_convention=ql.ModifiedFollowing):
        super().__init__(valuationdate,quote,'Futures')
        self.calendar=calendar
        self.daycount=daycount
        period=ql.Period(int(settledays),ql.Days)
        spotdate=self.calendar.advance(valuationdate,period,bussinessday_convention)
        if futuretype=='IMM':
            imm=ql.IMM_nextDate(spotdate)
            for i in range(futureindex-1):
                imm=ql.IMM_nextDate(imm+1)               
        elif futuretype=='ASX':
            imm=ql.ASX_nextDate(spotdate)
            for i in range(futureindex-1):
                imm=ql.ASX_nextDate(imm+1)
        self.startdate=imm
        period=ql.Period(length,ql.Months)
        self.enddate=self.calendar.advance(self.startdate,period,bussinessday_convention,True)
        self.discurve=discurve

    def impliedquote(self):
        yearfrac=self.daycount.yearFraction(self.startdate,self.enddate)
        rate=(self.curve.QLZeroCurve.discount(self.startdate) \
                    /self.curve.QLZeroCurve.discount(self.enddate)-1)/yearfrac
        return 1.-rate

    def registerindex(self,index):
        self.index=index

    def assigncurves(self, curves):
        self.curve=curves[self.discurve]
        self.curve.register(self.index)

class SWAP(instrument):   #single currency fix-float swap
    def __init__(self,
                 valuationdate,
                 quote,             #fixed leg rate
                 maturity,          #string for the tenor, e.g. '3M'                 
                 paymentcalendar,
                 fixingcalendar,
                 settledays,
                 businessday_convention=None,
                 Leg1daycount=None,
                 Leg1Frequency=None, #following arguments are for swaps             
                 Leg1forcurve=None,  #forcasting curve name
                 Leg1discurve=None,  #discounting curve name
                 Leg2daycount=None,
                 Leg2Frequency=None,
                 Leg2forcurve=None,  #must be provided
                 Leg2discurve=None): #must be provided
        super().__init__(valuationdate,quote,'SWAP')
        self.maturity=maturity
        self.leg1daycount=Leg1daycount
        self.leg2daycount=Leg2daycount
        self.paymentcalendar=paymentcalendar
        self.fixingcalendar=fixingcalendar
        self.settledays=int(settledays)
        self.Leg1Frequency=Leg1Frequency
        self.Leg2Frequency=Leg2Frequency
        self.Leg1discurve=Leg1discurve
        self.Leg2discurve=Leg2discurve
        self.Leg1forcurve=Leg1forcurve
        self.Leg2forcurve=Leg2forcurve
        self.businessday_convention=businessday_convention
        period=ql.Period(int(settledays),ql.Days)
        self.startdate=self.paymentcalendar.advance(valuationdate,period)
        period=ql.Period(maturity)
        self.enddate=self.paymentcalendar.advance(self.startdate,period,businessday_convention,True)
               
    def impliedquote(self):
        impliedquote=self.QLSWAP.fairRate()
        return impliedquote

    def registerindex(self, index):
        self.index=index
    
    def assigncurves(self, curves):
        self.forcurve=curves[self.Leg2forcurve]
        self.discurve=curves[self.Leg2discurve]
        self.IBORIndex=ql.IborIndex('IborIndex',
                          ql.Period(self.Leg2Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.fixingcalendar,
                          ql.ModifiedFollowing,
                          False,
                          self.leg2daycount,
                          self.forcurve.QLZeroCurve)
        fixedschedule=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg1Frequency),
                             self.paymentcalendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Backward,
                             False)
        floatingschedule=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg2Frequency),
                             self.paymentcalendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Backward,
                             False)
        self.QLSWAP=ql.VanillaSwap(ql.VanillaSwap.Payer,
                            1000000.0,
                            fixedschedule,
                            self.quote,
                            self.leg1daycount,
                            floatingschedule,
                            self.IBORIndex,
                            0.0,
                            self.leg2daycount)
        engine=ql.DiscountingSwapEngine(self.discurve.QLZeroCurve)
        self.QLSWAP.setPricingEngine(engine)
        self.discurve.register(self.index)
        self.forcurve.register(self.index)


class BSSWAP(instrument):   #single currency float-float basis swap
    def __init__(self,
                 valuationdate,
                 quote,             #fixed leg rate
                 maturity,          #string for the tenor, e.g. '3M'
                 daycount,
                 calendar,
                 settledays,
                 businessday_convention=None,
                 Leg1Frequency=None, #following arguments are for swaps             
                 Leg1forcurve=None,  #forcasting curve name
                 Leg1discurve=None,  #discounting curve name
                 Leg2Frequency=None,
                 Leg2forcurve=None,
                 Leg2discurve=None):
        super().__init__(valuationdate,quote,'BS')
        self.maturity=maturity
        self.daycount=daycount
        self.calendar=calendar
        self.settledays=int(settledays)
        self.Leg1Frequency=Leg1Frequency
        self.Leg2Frequency=Leg2Frequency
        self.Leg1discurve=Leg1discurve
        self.Leg2discurve=Leg2discurve
        self.Leg1forcurve=Leg1forcurve
        self.Leg2forcurve=Leg2forcurve
        self.businessday_convention=businessday_convention
        period=ql.Period(int(settledays),ql.Days)
        self.startdate=self.calendar.advance(valuationdate,period)
        period=ql.Period(maturity)
        self.enddate=self.calendar.advance(self.startdate,period,businessday_convention,True)

    def impliedquote(self):
        NPV1=self.QLSWAP1.NPV()
        NPV2=self.QLSWAP2.NPV()
        bp=1e-4
        impliedquote=(NPV2-NPV1)/self.QLSWAP1.floatingLegBPS()*bp \
            /self.zdiscurve2.QLZeroCurve.discount(self.startdate)
        impliedquote+=self.quote
        return impliedquote
    
    def registerindex(self, index):
        self.index=index
    def assigncurves(self, curves):
        self.zLeg1forcurve=curves[self.Leg1forcurve]
        self.zLeg2forcurve=curves[self.Leg2forcurve]
        self.zdiscurve1=curves[self.Leg1discurve]
        self.zdiscurve2=curves[self.Leg2discurve]
        self.IBORIndex1=ql.IborIndex('IborIndex1',
                          ql.Period(self.Leg1Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.calendar,
                          ql.ModifiedFollowing,
                          False,
                          self.daycount,
                          self.zLeg1forcurve.QLZeroCurve)
        self.IBORIndex2=ql.IborIndex('IborIndex2',
                          ql.Period(self.Leg2Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.calendar,
                          ql.ModifiedFollowing,
                          False,
                          self.daycount,
                          self.zLeg2forcurve.QLZeroCurve)
        schedule1=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg1Frequency),
                             self.calendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Backward,
                             False)
        schedule2=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg2Frequency),
                             self.calendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Backward,
                             False)
        self.QLSWAP1=ql.VanillaSwap(ql.VanillaSwap.Payer,
                            1000000.0,
                            schedule1,
                            0.0,
                            self.daycount,
                            schedule1,
                            self.IBORIndex1,
                            self.quote,
                            self.daycount)
        self.QLSWAP2=ql.VanillaSwap(ql.VanillaSwap.Payer,
                            1000000.0,
                            schedule2,
                            0.0,
                            self.daycount,
                            schedule2,
                            self.IBORIndex2,
                            0.0,
                            self.daycount)
        engine=ql.DiscountingSwapEngine(self.zdiscurve1.QLZeroCurve)
        self.QLSWAP1.setPricingEngine(engine)
        engine2=ql.DiscountingSwapEngine(self.zdiscurve2.QLZeroCurve)
        self.QLSWAP2.setPricingEngine(engine2)
        self.zdiscurve1.register(self.index)
        if(self.Leg1discurve!=self.Leg2discurve):
            self.zdiscurve2.register(self.index)
        self.zLeg1forcurve.register(self.index)
        self.zLeg2forcurve.register(self.index)

    
class OIS(instrument):
    def __init__(self,
                 valuationdate,
                 quote,             #fixed leg rate
                 maturity,          #string for the tenor, e.g. '3M'
                 daycount,
                 calendar,
                 settledays,
                 paymentlag=2,
                 businessday_convention=ql.Following,
                 Frequency=None, #following arguments are for swaps             
                 curve=None,  #forcasting curve name
                 ):
        super().__init__(valuationdate,quote,'OIS')
        self.maturity=maturity
        self.daycount=daycount
        self.calendar=calendar
        self.settledays=int(settledays)
        self.Frequency=Frequency
        self.curve=curve
        self.businessday_convention=businessday_convention
        period=ql.Period(int(settledays),ql.Days)
        self.startdate=self.calendar.advance(valuationdate,period)
        period=ql.Period(maturity)
        self.maturitydate=self.calendar.advance(self.startdate,period)
        period=ql.Period(int(paymentlag),ql.Days)
        self.enddate=self.calendar.advance(self.maturitydate,period)
        self.paymentlag=int(paymentlag)
       

    def impliedquote(self):
        impliedquote=self.QLOIS.fairRate()
        return impliedquote

    def registerindex(self, index):
        self.index=index

    def assigncurves(self, curves):
        self.zcurve=curves[self.curve]
        self.onindex=ql.OvernightIndex('onindex',
                          self.settledays,
                          ql.USDCurrency(),
                          self.calendar,
                          self.daycount,
                          self.zcurve.QLZeroCurve)
        schedule=ql.Schedule(self.startdate,
                             self.maturitydate,
                             ql.Period(self.Frequency),
                             self.calendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Backward,
                             False)
        self.QLOIS=ql.OvernightIndexedSwap(ql.OvernightIndexedSwap.Payer,
                                            1000000.0,
                                            schedule,
                                            self.quote,
                                            self.daycount,
                                            self.onindex,
                                            0.0,
                                            self.paymentlag)
        engine=ql.DiscountingSwapEngine(self.zcurve.QLZeroCurve)
        self.QLOIS.setPricingEngine(engine)
        self.zcurve.register(self.index)
class CCS(instrument):   #cross currency swap, can be fix-float or float-float and resettble
    def __init__(self,
                 valuationdate,
                 quote,             #fixed leg rate
                 maturity,          #string for the tenor, e.g. '3M'
                 settledays,
                 businessday_convention=None,
                 Leg1Daycount=None,
                 Leg1Frequency=None, #following arguments are for swaps             
                 Leg1forcurve=None,  #forcasting curve name
                 Leg1discurve=None,  #discounting curve name
                 Leg1FixingCalendar=None,
                 Leg1PaymentCalendar=None,
                 Leg2Daycount=None,
                 Leg2Frequency=None,
                 Leg2forcurve=None,
                 Leg2discurve=None,
                 Leg2FixingCalendar=None,
                 Leg2PaymentCalendar=None,
                 resettable=False,
                 resettableleg=None):
        super().__init__(valuationdate,quote,'CCS')
        self.maturity=maturity
        self.settledays=int(settledays)
        self.Leg1Daycount=Leg1Daycount
        self.Leg2Daycount=Leg2Daycount
        self.Leg1Frequency=Leg1Frequency
        self.Leg2Frequency=Leg2Frequency
        self.Leg1discurve=Leg1discurve
        self.Leg2discurve=Leg2discurve
        self.Leg1forcurve=Leg1forcurve
        self.Leg2forcurve=Leg2forcurve
        self.Leg1FixingCalendar=Leg1FixingCalendar
        self.Leg2FixingCalendar=Leg2FixingCalendar
        self.Leg1PaymentCalendar=Leg1PaymentCalendar
        self.Leg2PaymentCalendar=Leg2PaymentCalendar
        self.businessday_convention=businessday_convention
        period=ql.Period(int(settledays),ql.Days)
        self.startdate=self.Leg1PaymentCalendar.advance(valuationdate,period)
        period=ql.Period(maturity)
        self.enddate=self.Leg1PaymentCalendar.advance(self.startdate,period)
        self.resettable=resettable
        self.resettableleg=resettableleg

    def Leg1BPS(self):
        schedule1=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg1Frequency),
                             self.Leg1PaymentCalendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Forward,
                             False)
        bp=1e-4
        dummyNotional1=[]
        Notional1=[]
        spread1=[]
        gearing1=[]
        fixedrate1=[]
        if self.Leg1forcurve!='None':  #float-float CCS
            for i, d in enumerate(schedule1):
                    dummyNotional1.append(0.)
                    if self.resettable and self.resettableleg==1:
                        notional=1000000
                        notional*=self.zdiscurve2.QLZeroCurve.discount(d)/self.zdiscurve1.QLZeroCurve.discount(d)
                        notional*=self.zdiscurve1.QLZeroCurve.discount(self.startdate)/self.zdiscurve2.QLZeroCurve.discount(self.startdate)
                        Notional1.append(notional)
                    else:
                        Notional1.append(1000000.)
                    gearing1.append(1.0)
                    spread1.append(self.quote+bp)
                    fixedrate1.append(0.0)
            dummyNotional1.pop()
            Notional1.pop()
            gearing1.pop()
            spread1.pop()
            fixedrate1.pop()
            swapType1=ql.VanillaSwap.Payer
            QLSWAP1bumped=ql.NonstandardSwap(swapType1,dummyNotional1,Notional1,schedule1,
                                              fixedrate1,self.Leg1Daycount,schedule1,self.IBORIndex1,
                                              gearing1,spread1,self.Leg1Daycount,True,True,
                                              ql.ModifiedFollowing)
        else:   #fixed-float CCS
            for i, d in enumerate(schedule1):
                    dummyNotional1.append(0.)
                    if self.resettable and self.resettableleg==1:
                        notional=1000000.
                        notional*=self.zdiscurve2.QLZeroCurve.discount(d)/self.zdiscurve1.QLZeroCurve.discount(d)
                        notional*=self.zdiscurve1.QLZeroCurve.discount(self.startdate)/self.zdiscurve2.QLZeroCurve.discount(self.startdate)
                        Notional1.append(notional)
                    else:
                        Notional1.append(1000000.)
                    gearing1.append(1.0)
                    spread1.append(0.0)
                    fixedrate1.append(self.quote+bp)
            dummyNotional1.pop()
            Notional1.pop()
            gearing1.pop()
            spread1.pop()
            fixedrate1.pop()
            swapType1=ql.VanillaSwap.Receiver
            QLSWAP1bumped=ql.NonstandardSwap(swapType1,Notional1,dummyNotional1,schedule1,
                                              fixedrate1,self.Leg1Daycount,schedule1,self.IBORIndex1,
                                              gearing1,spread1,self.Leg1Daycount,True,True,
                                              ql.ModifiedFollowing)
        engine1=ql.DiscountingSwapEngine(self.zdiscurve1.QLZeroCurve)
        QLSWAP1bumped.setPricingEngine(engine1)
        legbps=(QLSWAP1bumped.NPV()-self.QLSWAP1.NPV())
        legbps/=self.zdiscurve1.QLZeroCurve.discount(self.startdate)
        return legbps
    
    def impliedquote(self):
        NPV1=self.QLSWAP1.NPV()/self.zdiscurve1.QLZeroCurve.discount(self.startdate)
        NPV2=self.QLSWAP2.NPV()/self.zdiscurve2.QLZeroCurve.discount(self.startdate)
        Leg1BPS=self.Leg1BPS()
        bp=1.e-4
        impliedquote=(NPV2-NPV1)/self.Leg1BPS()*bp
        impliedquote+=self.quote
        return impliedquote
    

    def registerindex(self, index):
        self.index=index

    def assigncurves(self, curves):
        if self.Leg1forcurve!='None':
            self.zLeg1forcurve=curves[self.Leg1forcurve]
        self.zLeg2forcurve=curves[self.Leg2forcurve]
        self.zdiscurve1=curves[self.Leg1discurve]
        self.zdiscurve2=curves[self.Leg2discurve]
        if self.Leg1forcurve!='None':
            self.IBORIndex1=ql.IborIndex('IborIndex1',
                          ql.Period(self.Leg1Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.Leg1FixingCalendar,
                          ql.ModifiedFollowing,
                          False,
                          self.Leg1Daycount,
                          self.zLeg1forcurve.QLZeroCurve)
        else:
            self.IBORIndex1=ql.IborIndex('IborIndex1',
                          ql.Period(self.Leg1Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.Leg1FixingCalendar,
                          ql.ModifiedFollowing,
                          False,
                          self.Leg1Daycount,
                          self.zdiscurve1.QLZeroCurve)
        self.IBORIndex2=ql.IborIndex('IborIndex2',
                          ql.Period(self.Leg2Frequency),
                          self.settledays,
                          ql.USDCurrency(),
                          self.Leg2FixingCalendar,
                          ql.ModifiedFollowing,
                          False,
                          self.Leg2Daycount,
                          self.zLeg2forcurve.QLZeroCurve)
        schedule1=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg1Frequency),
                             self.Leg1PaymentCalendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Forward,
                             False)
        # The first swap has zero notional on the second leg if the CCS is fixed vs floating and it is a receiver swap. 
        # Or zero notional on the first leg if the CCS is float vs floating and it is a payer swap.
        # 
        # Second swap has zero notional on the first leg, the second leg is floating. it is a payer swap. 
        dummyNotional1=[]
        Notional1=[]
        spread1=[]
        gearing1=[]
        fixedrate1=[]

        if self.Leg1forcurve!='None':  #float-float CCS
            for i, d in enumerate(schedule1):
                    dummyNotional1.append(0.)
                    if self.resettable and self.resettableleg==1:
                        notional=1000000
                        notional*=self.zdiscurve2.QLZeroCurve.discount(d)/self.zdiscurve1.QLZeroCurve.discount(d)
                        notional*=self.zdiscurve1.QLZeroCurve.discount(self.startdate)/self.zdiscurve2.QLZeroCurve.discount(self.startdate)
                        Notional1.append(notional)
                    else:
                        Notional1.append(1000000.) 
                    gearing1.append(1.0)
                    spread1.append(self.quote)
                    fixedrate1.append(0.0)
            dummyNotional1.pop()
            Notional1.pop()
            gearing1.pop()
            spread1.pop()
            fixedrate1.pop()
            swapType1=ql.VanillaSwap.Payer
            self.QLSWAP1=ql.NonstandardSwap(swapType1,dummyNotional1,Notional1,schedule1,
                                              fixedrate1,self.Leg1Daycount,schedule1,self.IBORIndex1,
                                              gearing1,spread1,self.Leg1Daycount,True,True,
                                              ql.ModifiedFollowing)
        else:   #fixed-float CCS
            for i, d in enumerate(schedule1):
                    dummyNotional1.append(0.)
                    if self.resettable and self.resettableleg==1: 
                        notional=1000000
                        notional*=self.zdiscurve2.QLZeroCurve.discount(d)/self.zdiscurve1.QLZeroCurve.discount(d)
                        notional*=self.zdiscurve1.QLZeroCurve.discount(self.startdate)/self.zdiscurve2.QLZeroCurve.discount(self.startdate)
                        Notional1.append(notional)
                    else:
                        Notional1.append(1000000.) 
                    gearing1.append(1.0)
                    spread1.append(0.0)
                    fixedrate1.append(self.quote)
            dummyNotional1.pop()
            Notional1.pop()
            gearing1.pop()
            spread1.pop()
            fixedrate1.pop()
            swapType1=ql.VanillaSwap.Receiver
            self.QLSWAP1=ql.NonstandardSwap(swapType1,Notional1,dummyNotional1,schedule1,
                                              fixedrate1,self.Leg1Daycount,schedule1,self.IBORIndex1,
                                              gearing1,spread1,self.Leg1Daycount,True,True,
                                              ql.ModifiedFollowing)
        schedule2=ql.Schedule(self.startdate,
                             self.enddate,
                             ql.Period(self.Leg2Frequency),
                             self.Leg2FixingCalendar,
                             ql.ModifiedFollowing,
                             ql.ModifiedFollowing,
                             ql.DateGeneration.Forward,
                             False)
        dummyNotional2=[]
        Notional2=[]
        spread2=[]
        gearing2=[]
        fixedrate2=[]
        for i, d in enumerate(schedule2):
            dummyNotional2.append(0.)
            if self.resettable and self.resettableleg==2: 
                notional=1000000.0
                notional*=self.zdiscurve1.QLZeroCurve.discount(d)/self.zdiscurve2.QLZeroCurve.discount(d)
                notional*=self.zdiscurve2.QLZeroCurve.discount(self.startdate)/self.zdiscurve1.QLZeroCurve.discount(self.startdate)
                Notional2.append(notional)

            else:
                Notional2.append(1000000.) 
            gearing2.append(1.0)
            spread2.append(0)
            fixedrate2.append(0.0)
        dummyNotional2.pop()
        Notional2.pop()
        gearing2.pop()
        spread2.pop()
        fixedrate2.pop()
        swapType2=ql.VanillaSwap.Payer
        self.QLSWAP2=ql.NonstandardSwap(swapType2,dummyNotional2,Notional2,schedule2,
                                              fixedrate2,self.Leg2Daycount,schedule2,self.IBORIndex2,
                                              gearing2,spread2,self.Leg2Daycount,True,True,
                                              ql.ModifiedFollowing)

        engine1=ql.DiscountingSwapEngine(self.zdiscurve1.QLZeroCurve)
        self.QLSWAP1.setPricingEngine(engine1)
        engine2=ql.DiscountingSwapEngine(self.zdiscurve2.QLZeroCurve)
        self.QLSWAP2.setPricingEngine(engine2)
        self.zdiscurve1.register(self.index)
        if(self.Leg1discurve!=self.Leg2discurve):
            self.zdiscurve2.register(self.index)
        if(self.Leg1forcurve!='None'):
            self.zLeg1forcurve.register(self.index)
        self.zLeg2forcurve.register(self.index)




class CurveSet(object):
    """description of class"""
    def __init__(self,valuationdate):
        self.curveset=OrderedDict()
        self.x0=[]      #initial guess
        self.instruments=[]
        self.quotes=[]
        self.calculated=False
        self.valuationdate=valuationdate
        
    def addcurve(self, name, curve):
        self.curveset[name]=curve
        self.x0+=self.curveset[name].zerorates

    def addinstrument(self, inst):
        #create quantlib ratehelper       
        self.instruments.append(inst)
        inst.registerindex(len(self.instruments)-1)
    

    def __costFunc(self,x):
        #initialize instruments
        n1=0
        for item in self.curveset:
            n2=len(self.curveset[item].zerorates)
            self.curveset[item].updateZeroRates(x[n1:n1+n2].tolist())
            n1=n1+n2
        N=len(self.instruments)
        error=np.zeros(N)
        for i in range(0,len(self.instruments)):
            impliedquote=self.instruments[i].impliedquote()
            error[i]=impliedquote-self.instruments[i].quote
        print(error)
        return error

    def jacobian(self,x):
        N=len(self.instruments)
        #assert(N==len(x)),'numbers of instruments and zerorates do not match'
        jacobian=np.zeros((N,N))
        itemsendindex={}
        n1=0
        for item in self.curveset:
            n2=len(self.curveset[item].zerorates)
            self.curveset[item].updateZeroRates(x[n1:n1+n2].tolist())
            itemsendindex[item]=n1+n2-1
            n1=n1+n2
        impliedquote=np.zeros(N)
        for i in range(0,len(self.instruments)):
            impliedquote[i]=self.instruments[i].impliedquote()
        eps=1e-6
        for i in range(0,len(x)):
            x[i]=x[i]+eps
            n1=0
            for item in itemsendindex:
                n2=len(self.curveset[item].zerorates)
                if i<=itemsendindex[item]:
                    shiftedcurve=item
                    self.curveset[shiftedcurve].updateZeroRates(x[n1:n1+n2].tolist())
                    break
                n1=n1+n2
            for j in self.curveset[shiftedcurve].observerindex:
                jacobian[j,i]=(self.instruments[j].impliedquote()-impliedquote[j])/eps
            x[i]=x[i]-eps
            self.curveset[item].updateZeroRates(x[n1:n1+n2].tolist())
        self.DRDZ=jacobian
        return jacobian
    
    def bootstrap(self):
        #assigncurves
        for curvename in self.curveset:
            self.curveset[curvename].updatedependency(self.curveset)
        for curvename in self.curveset:
            self.curveset[curvename].initializeQLZeroCurve()

        for item in self.instruments:
            item.assigncurves(self.curveset)
        
        for curvename in self.curveset:
            self.curveset[curvename].consolidateinstrument()       

        res=least_squares(self.__costFunc,self.x0,jac=self.jacobian, method='lm',ftol=1e-10, max_nfev=100)
        self.calculated=True


    def getcurve(self,name):
        return self.curveset[name]

    def writezerostoExcel(self,wb):
        '''write the zero curve to Excel'''
        sht=wb.sheets['ZeroCurves']
        i=0
        for curvename in self.curveset.keys():
            sht.range((1,i*3+1)).value=curvename
            sht.range((2,i*3+1)).options(transpose=True).value=self.curveset[curvename].tenors
            maturities=[]
            for j in self.curveset[curvename].tenordates:
                maturities.append(j.serialNumber())
            sht.range((2,i*3+2)).options(transpose=True).value=maturities
            sht.range((2,i*3+3)).options(transpose=True).value=self.curveset[curvename].zerorates
            i+=1

    def writeJacobiantoExcel(self,wb):
        '''write the Jacobian matrix to Excel'''
        sht=wb.sheets['JacobianMatrix']
        i=0
        for curvename in self.curveset.keys():
            lables=[curvename+tenor for tenor in self.curveset[curvename].tenors]
            sht.range((3+i,2)).options(transpose=True).value=lables
            sht.range((2,3+i)).value=lables
            i+=len(self.curveset[curvename].tenors)

        sht.range((3,3)).options(transpose=True).value=self.DRDZ
        invjacobian=inv(self.DRDZ)
        sht=wb.sheets['InvJacobianMatrix']
        i=0
        for curvename in self.curveset.keys():
            lables=[curvename+tenor for tenor in self.curveset[curvename].tenors]
            sht.range((3+i,2)).options(transpose=True).value=lables
            sht.range((2,3+i)).value=lables
            i+=len(self.curveset[curvename].tenors)

        sht.range((3,3)).options(transpose=True).value=invjacobian
        
        
        


