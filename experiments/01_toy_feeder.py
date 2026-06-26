# OpenDSSDirect: Python bindings for OpenDSS (Distribution System Simulator).
# `dss(...)` executes OpenDSS text commands; `dss.Circuit`, `dss.Solution`, etc.
# expose results and solver controls after the model is built.
from opendssdirect import dss


def build_toy_feeder(pv_kw: float = 0.0, ev_kw: float = 0.0):
    """
    Build a minimal 3-phase radial distribution feeder in OpenDSS and solve power flow.

    Topology (fixed skeleton):
        sourcebus --L1 (1 km)-- bus1 --L2 (1 km)-- bus2
        Load1 at bus1 (500 kW), Load2 at bus2 (300 kW)

    Optional DER at bus2 (far end, usually weakest voltage):
        pv_kw  -> PVSystem injection (supports local voltage)
        ev_kw  -> additional Load (EV charging, stresses voltage)

    Returns nothing; results live in the OpenDSS circuit until the next Clear/Solve.
    """
    # Core network: substation source, two line segments, two constant-P/Q loads.
    # All OpenDSS lines starting with `!` are comments (ignored by the solver).
    dss("""
    ! Reset OpenDSS memory. Required because __main__ calls this function multiple
    ! times; without Clear, elements (L1, Load1, ...) would stack and corrupt results.
    Clear

    ! Create the top-level circuit container named ToyFeeder.
    ! basekv=12.47  -> nominal line-to-line voltage (kV); common US MV distribution level.
    ! pu=1.0        -> slack/reference bus held at 100% of nominal voltage.
    ! phases=3      -> balanced three-phase (A/B/C) system.
    ! bus1=sourcebus -> name of the substation/slack bus at the feeder head.
    New Circuit.ToyFeeder basekv=12.47 pu=1.0 phases=3 bus1=sourcebus

    ! OpenDSS auto-creates Vsource.Source with every new circuit; Edit configures it.
    ! bus1=sourcebus.1.2.3 -> tie the ideal voltage source to all three phase nodes.
    ! basekv / pu=1.0      -> stiff 12.47 kV source (infinite-strength grid equivalent).
    ! angle=30             -> reference phase angle (deg); sets the solver's angle frame.
    Edit Vsource.Source bus1=sourcebus.1.2.3 basekv=12.47 pu=1.0 phases=3 angle=30

    ! Linecode = reusable per-length impedance template (conductor type, not topology).
    ! r1, x1   -> positive-sequence resistance/reactance (ohm/km); dominate balanced flow.
    ! r0, x0   -> zero-sequence values; used for unbalanced/fault studies, stored here too.
    ! units=km -> r1/x1/r0/x0 are multiplied by Line.length to get segment impedance Z.
    New Linecode.simple nphases=3 r1=0.306 x1=0.627 r0=0.592 x0=1.42 units=km

    ! Line L1: first segment from substation to mid-feeder bus1 (1 km of `simple`).
    ! Voltage drop along L1: dV ~ I * (r1 + j*x1) * length under load current I.
    New Line.L1 bus1=sourcebus.1.2.3 bus2=bus1.1.2.3 phases=3 linecode=simple length=1 units=km
    ! Line L2: second segment from bus1 to far-end bus2 (another 1 km, same conductor).
    ! bus2 typically has the lowest voltage in this radial chain (two drops + local load).
    New Line.L2 bus1=bus1.1.2.3 bus2=bus2.1.2.3 phases=3 linecode=simple length=1 units=km

    ! Load1 at bus1: wye-connected constant-power load (default OpenDSS load model).
    ! conn=wye -> line-to-neutral connection; kv is line-to-line rating (12.47 kV).
    ! kw/kvar  -> active and reactive demand; pf ~ 0.96 lagging (500 kW, 150 kVAr).
    New Load.Load1 bus1=bus1.1.2.3 phases=3 conn=wye kv=12.47 kw=500 kvar=150
    ! Load2 at bus2 (feeder tail): 300 kW + 100 kVAr; sees cumulative drop from L1+L2.
    New Load.Load2 bus1=bus2.1.2.3 phases=3 conn=wye kv=12.47 kw=300 kvar=100

    ! Declare nominal voltage levels for per-unit (pu) reporting: V_pu = V_actual / V_base.
    Set VoltageBases=[12.47]
    ! Assign pu bases to every bus/element so AllBusMagPu and limits (0.95-1.05) are meaningful.
    CalcVoltageBases
    """)

    # Optional PV at bus2: negative net load / generation injection on the far bus.
    # Only added when pv_kw > 0 so the base case stays load-only.
    if pv_kw > 0:
        dss(f"""
        ! PVSystem model: inverter-connected solar at bus2, all three phases.
        New PVSystem.PV_bus2
        ~ phases=3
        ~ bus1=bus2.1.2.3
        ! kv must match local distribution voltage for correct power conversion.
        ~ kv=12.47
        ! kva = inverter nameplate (kVA); pmpp = max active power at full irradiance (kW).
        ~ kva={pv_kw}
        ~ pmpp={pv_kw}
        ! irradiance=1 -> 100% sun; pf=1 -> unity power factor (no reactive output).
        ~ irradiance=1
        ~ pf=1
        """)

    # Optional EV charging at bus2: extra constant-P load stacked on Load2.
    # kvar=0 -> unity pf charging; increases current and voltage drop on L1+L2.
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

    # Run the power-flow solver (balanced 3-phase by default for this model).
    # Populates bus voltages, line flows, and losses used by voltage_summary().
    dss.Solution.Solve()


def voltage_summary():
    """
    Summarize post-solve bus voltage magnitudes in per unit.

    Uses ANSI-style utilization band 0.95-1.05 pu as a simple violation flag.
    Returns dict with min/max pu and whether any bus is outside that band.
    """
    # AllBusMagPu: magnitude of each bus node voltage relative to its assigned base.
    volts_pu = list(dss.Circuit.AllBusMagPu())
    return {
        "min_v_pu": min(volts_pu),
        "max_v_pu": max(volts_pu),
        # True if any bus sags below 95% or swells above 105% of nominal.
        "voltage_violation": min(volts_pu) < 0.95 or max(volts_pu) > 1.05,
    }


if __name__ == "__main__":
    # Scenario 1: base case — fixed loads only, no DER at bus2.
    build_toy_feeder(pv_kw=0, ev_kw=0)
    print("Base case:", voltage_summary())

    # Scenario 2: 500 kW PV at bus2 — injection should raise far-end voltage.
    build_toy_feeder(pv_kw=500, ev_kw=0)
    print("With 500 kW PV:", voltage_summary())

    # Scenario 3: 500 kW EV charging at bus2 — extra load should depress voltage further.
    build_toy_feeder(pv_kw=0, ev_kw=500)
    print("With 500 kW EV:", voltage_summary())
