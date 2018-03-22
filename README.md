# MultiCurveBuilding
# Author: Wang Qian
# Company: United Overseas Bank, Singapore
# Email: qwang007@gmail.com

This is a tool in Python for bootstrapping mutli interest curves simutaneously. This tool utilize Python QuantLib package, with OvernightindexedSwap exported. To build multicurves, QuantLib bootstraps them one-by-one. In this tool,  we utilize multivariate optimization supported by Scipy. It has the follooing advantages:
   1 One does not need to know the order of curves in curve building.
   2 This tool is able to deal with the situation in which multi curves have inter-dependency. 
   3 The general definition of instruments in QuatLib are used, giving more flexibility than the ratehelpers in QuantLib.
   4 As a by-product of the optimization method, the Jacobian matrix is produced. The Jacobian matrix and its invervser can be used 
     to covert the zero PV01 to Par PV01 and vice versa.

Following curve building instruments are defined in the tool: 
  Deposit, 
  FRA, 
  Futures, 
  Swap, 
  Basis Swap, 
  Cross Currency Swap, 
  OvernightindexedSwap

At this stage, only Zero Curve and Zero Spread curve are supported. The interpoation method is Linear in zero rates. 
The CurveSet.py and ZeroCurve.py provide the intruments definitions, curve building methods, curves definitions. The CurveBuilding.py file is a sample testing file.  
