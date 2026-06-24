from opendssdirect import dss


def build_toy_feeder(pv_kw: float = 0.0, ev_kw: float = 0.0):
    dss("""
    Clear

    New Circuit.ToyFeeder basekv=12.47 pu=1.0 phases=3 bus1=sourcebus

    Edit Vsource.Source bus1=sourcebus.1.2.3 basekv=12.47 pu=1.0 phases=3 angle=30

    New Linecode.simple nphases=3 r1=0.306 x1=0.627 r0=0.592 x0=1.42 units=km

    New Line.L1 bus1=sourcebus.1.2.3 bus2=bus1.1.2.3 phases=3 linecode=simple length=1 units=km
    New Line.L2 bus1=bus1.1.2.3 bus2=bus2.1.2.3 phases=3 linecode=simple length=1 units=km

    New Load.Load1 bus1=bus1.1.2.3 phases=3 conn=wye kv=12.47 kw=500 kvar=150
    New Load.Load2 bus1=bus2.1.2.3 phases=3 conn=wye kv=12.47 kw=300 kvar=100

    Set VoltageBases=[12.47]
    CalcVoltageBases
    """)

    if pv_kw > 0:
        dss(f"""
        New PVSystem.PV_bus2
        ~ phases=3
        ~ bus1=bus2.1.2.3
        ~ kv=12.47
        ~ kva={pv_kw}
        ~ pmpp={pv_kw}
        ~ irradiance=1
        ~ pf=1
        """)

    if ev_kw > 0:
        dss(f"""
        New Load.EV_bus2
        ~ bus1=bus2.1.2.3
        ~ phases=3
        ~ conn=wye
        ~ kv=12.47
        ~ kw={ev_kw}
        ~ kvar=0
        """)

    dss.Solution.Solve()


def voltage_summary():
    # Per-unit voltage magnitudes at all bus nodes.
    # OpenDSSDirect exposes AllBusMagPu for this.
    volts_pu = list(dss.Circuit.AllBusMagPu())
    return {
        "min_v_pu": min(volts_pu),
        "max_v_pu": max(volts_pu),
        "voltage_violation": min(volts_pu) < 0.95 or max(volts_pu) > 1.05,
    }


if __name__ == "__main__":
    build_toy_feeder(pv_kw=0, ev_kw=0)
    print("Base case:", voltage_summary())

    build_toy_feeder(pv_kw=500, ev_kw=0)
    print("With 500 kW PV:", voltage_summary())

    build_toy_feeder(pv_kw=0, ev_kw=500)
    print("With 500 kW EV:", voltage_summary())