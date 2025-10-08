def getAvailableTickets():
    from ibapi.ticktype import TickTypeEnum # type: ignore

    for i in range(91):
	    print(TickTypeEnum.toStr(i), i)