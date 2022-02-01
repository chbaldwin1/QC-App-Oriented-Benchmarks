"""
Amplitude Estimation Benchmark Program via Phase Estimation - Braket
"""
import time
import sys
import numpy as np
from ae_utils import adjoint, controlled_unitary
from braket.circuits import Circuit
from braket.circuits.unitary_calculation import calculate_unitary

sys.path[1:1] = ["_common", "_common/braket", "quantum-fourier-transform/braket"]
sys.path[1:1] = ["../../_common", "../../_common/braket", "../../quantum-fourier-transform/braket"]
import execute as ex
import metrics as metrics
from qft_benchmark import inv_qft_gate

np.random.seed(0)

verbose = False

# saved subcircuits circuits for printing
A_ = None
Q_ = None
cQ_ = None
QC_ = None
QFTI_ = None

# On Braket some devices don't support cu1 (cphaseshift)  
_use_cu1_shim = False

############### Circuit Definition

def AmplitudeEstimation(num_state_qubits, num_counting_qubits, a, psi_zero=None, psi_one=None):
    qc = Circuit()

    num_qubits = num_state_qubits + 1 + num_counting_qubits

    qubits = list(range(num_qubits))

    # create the Amplitude Generator circuit
    A = A_gen(num_state_qubits, a, psi_zero, psi_one)

    # create the Quantum Operator circuit and a controlled version of it
    Q_unitary, Q = Q_Unitary(num_state_qubits, A)

    # save small example subcircuits for visualization
    global A_, Q_, cQ_, QFTI_
    if (cQ_ and Q_) == None or num_state_qubits <= 6:
        if num_state_qubits < 9: 
            sample_controlled_unitary = controlled_unitary(
                control=qubits[0],
                targets=[qubits[l] for l in range(num_counting_qubits, num_qubits)],
                unitary=Q_unitary,
                display_name="CQ"
            )
            
            cQ_ = sample_controlled_unitary; Q_ = Q; A_ = A
    if QFTI_ == None or num_qubits <= 5:
        if num_qubits < 9: QFTI_ = inv_qft_gate(num_counting_qubits)
    
    # Prepare state A, and counting qubits with H transform
    # counting range = range(num_counting)
    # state range = range(num_counting, num_counting + num_state)
    # objective qubit = -1 or range(num_counting + num_state, num_qubits)
    # state and objective range = range(num_counting, num_qubits)
    qc.add_circuit(A, target=list(range(num_counting_qubits, num_qubits)))
    for i in range(num_counting_qubits):
        qc.h(qubits[i])
    
    repeat = 1
    for j in reversed(range(num_counting_qubits)):
        for _ in range(repeat):
            qc.add_circuit(
                controlled_unitary(
                    control=qubits[j],
                    targets=[qubits[l] for l in range(num_counting_qubits, num_qubits)],
                    unitary=Q_unitary,
                    display_name="CQ"
                )
            )
        repeat *= 2
    
    # Inverse quantum Fourier transofrm only on counting qubits
    qc.add_circuit(inv_qft_gate(num_counting_qubits))

    # save smaller circuit example for display
    global QC_
    if QC_ == None or num_qubits <= 5:
        if num_qubits < 9: QC_ = qc
    
    return qc

# Construct A operator that takes |0>_{n+1} to sqrt(1-a) |psi_0>|0> + sqrt(a) |psi_1>|1>
def A_gen(num_state_qubits, a, psi_zero=None, psi_one=None):
    
    if psi_zero == None:
        psi_zero = '0'*num_state_qubits
    if psi_one == None:
        psi_one = '1'*num_state_qubits

    theta = 2 * np.arcsin(np.sqrt(a))

    # Let the objective be qubit index n; state is on qubits 0 through n-1
    qc_A = Circuit()

    # takes state to |0>_{n} (sqrt(1-a) |0> + sqrt(a) |1>)
    qc_A.ry(num_state_qubits, theta)

    # takes state to sqrt(1-a) |psi_0>|0> + sqrt(a) |0>_{n}|1>
    qc_A.x(num_state_qubits)
    for i in range(num_state_qubits):
        if psi_zero[i] == '1':
            qc_A.cnot(control=num_state_qubits, target=i)
    qc_A.x(num_state_qubits)

    # takes state to sqrt(1-a) |psi_0>|0> + sqrt(a) |psi_1>|1>
    for i in range(num_state_qubits):
        if psi_one[i] == '1':
            qc_A.cnot(control=num_state_qubits, target=i)
    
    return qc_A

# Construct the gover-like operator
def Q_Unitary(num_state_qubits, A_circ):
    
    # index n is the objective qubit, and indexes 0 through n-1 are state qubits
    qc_Q = Circuit()
    
    temp_A = A_circ.copy()
    A_inverse = adjoint(temp_A)

    ### Each cycle in Q applies in order: -S_chi, A_circ_inverse, S_0, A_circ
    # -S_chi
    qc_Q.x(num_state_qubits)
    qc_Q.z(num_state_qubits)
    qc_Q.x(num_state_qubits)

    # A_circ_inverse
    qc_Q.add_circuit(A_inverse)

    # S_0
    for i in range(num_state_qubits + 1):
        qc_Q.x(i)
    qc_Q.h(num_state_qubits)

    # Apply MCX gate
    add_mcx(qc_Q, [x for x in range(num_state_qubits)], num_state_qubits)

    qc_Q.h(num_state_qubits)
    for i in range(num_state_qubits + 1):
        qc_Q.x(i)

    # A_circ
    qc_Q.add_circuit(temp_A, target=list(range(num_state_qubits + 1)))

    # Calculate unitary matrix representation
    Q_matrix_rep = calculate_unitary(qc_Q.qubit_count, qc_Q.instructions)

    # Returning just the matrix representation, to create a controlled unitary,
    # we need to pass the control when the circuit is formed
    return Q_matrix_rep, qc_Q

############### CPHASESHIFT shim 

# a CU1 or CPHASESHIFT equivalent
def add_cphaseshift(qc, control, target, theta):
    qc.rz(control, theta/2)
    qc.cnot(control, target)
    qc.rz(target, -theta/2)
    qc.cnot(control, target)
    qc.rz(target, theta/2)
    
############### MCX shim

# single cx / cu1 unit for mcx implementation
def add_cx_unit(qc, cxcu1_unit, controls, target):
    num_controls = len(controls)
    i_qubit = cxcu1_unit[1]
    j_qubit = cxcu1_unit[0]
    theta = cxcu1_unit[2]
    
    if j_qubit != None:
        qc.cnot(controls[j_qubit], controls[i_qubit]) 
        
    #qc.cu1(theta, controls[i_qubit], target)
    if _use_cu1_shim:
        add_cphaseshift(qc, controls[i_qubit], target, theta)
    else:
        qc.cphaseshift(controls[i_qubit], target, theta)
    
    i_qubit = i_qubit - 1
    if j_qubit == None:
        j_qubit = i_qubit + 1
    else:
        j_qubit = j_qubit - 1
        
    if theta < 0:
        theta = -theta
    
    new_units = []
    if i_qubit >= 0:
        new_units += [ [ j_qubit, i_qubit, -theta ] ]
        new_units += [ [ num_controls - 1, i_qubit, theta ] ]
        
    return new_units

# mcx recursion loop 
def add_cxcu1_units(qc, cxcu1_units, controls, target):
    new_units = []
    for cxcu1_unit in cxcu1_units:
        new_units += add_cx_unit(qc, cxcu1_unit, controls, target)
    cxcu1_units.clear()
    return new_units

# mcx gate implementation: brute force and inefficient
# start with a single CU1 on last control and target
# and recursively expand for each additional control
def add_mcx(qc, controls, target):
    num_controls = len(controls)
    theta = np.pi / 2**num_controls
    qc.h(target)
    cxcu1_units = [ [ None, num_controls - 1, theta] ]
    while len(cxcu1_units) > 0:
        cxcu1_units += add_cxcu1_units(qc, cxcu1_units, controls, target)
    qc.h(target)

############### Analysis

# Analyze and print measured results
# Expected result is always the secret_int, so fidelity calc is simple
def analyze_and_print_result(qc, result, num_counting_qubits, s_int):
    
    # Braket measures all qubits, we need to remove the state qubits
    counts_r = result.measurement_counts
    counts_str = {}
    for measurement_r in counts_r.keys():
        measurement = measurement_r[:num_counting_qubits][::-1] # remove state qubits and reverse order
        if measurement in counts_str:
            counts_str[measurement] += counts_r[measurement_r]
        else:
            counts_str[measurement] = counts_r[measurement_r]
    
    counts = bitstring_to_a(counts_str, num_counting_qubits)
    a = a_from_s_int(s_int, num_counting_qubits)

    if verbose: print(f"For amplitude {a} measure: {counts}")

    # correct distribution is measuring ampltiude a 100% of the time
    correct_dist = {a: 1.0}

    # generate thermal_dist with amplitudes instead, to be comparable to correct dist
    bit_thermal_dist = metrics.uniform_dist(num_counting_qubits)
    thermal_dist = bitstring_to_a(bit_thermal_dist, num_counting_qubits)

    # use our polarization fidelity rescaling
    fidelity = metrics.polarization_fidelity(counts, correct_dist, thermal_dist)

    return counts, fidelity


def bitstring_to_a(counts, num_counting_qubits):
    est_counts = {}
    m = num_counting_qubits
    precision = int(num_counting_qubits / (np.log2(10))) + 2
    for key in counts.keys():
        r = counts[key]
        num = int(key,2) / (2**m)
        a_est = round((np.sin(np.pi * num) )** 2, precision)
        if a_est not in est_counts.keys():
            est_counts[a_est] = 0
        est_counts[a_est] += r
    return est_counts


def a_from_s_int(s_int, num_counting_qubits):
    theta = s_int * np.pi / (2**num_counting_qubits)
    precision = int(num_counting_qubits / (np.log2(10))) + 2
    a = round(np.sin(theta)**2, precision)
    return a

################ Benchmark Loop

# Because circuit size grows significantly with num_qubits
# limit the max_qubits here ...
MAX_QUBITS=8

# Execute program with default parameters
def run(min_qubits=3, max_qubits=8, max_circuits=3, num_shots=100,
        num_state_qubits=1, # default, not exposed to users
        backend_id='simulator', use_cu1_shim=False):
    
    print("Amplitude Estimation Benchmark Program - Braket")

    # Clamp the maximum number of qubits
    if max_qubits > MAX_QUBITS:
        print(f"INFO: Amplitude Estimation benchmark is limited to a maximum of {MAX_QUBITS} qubits.")
        max_qubits = MAX_QUBITS
    
    # validate parameters (smallest circuit is 3 qubits)
    num_state_qubits = max(1, num_state_qubits)
    if max_qubits < num_state_qubits + 2:
        print(f"ERROR: AE Benchmark needs at least {num_state_qubits + 2} qubits to run")
        return
    min_qubits = max(max(3, min_qubits), num_state_qubits + 2)

    # set the flag to use a cu1 (cphaseshift) shim if given, or for devices that don't support it
    global _use_cu1_shim
    if "ionq/" in backend_id: use_cu1_shim=True
    _use_cu1_shim = use_cu1_shim
    if _use_cu1_shim:
        print("... using CPHASESHIFT shim")

    # Initialize metrics module
    metrics.init_metrics()

    # define custom result handler
    def execution_handler(qc, result, num_qubits, s_int):

        # determine fidelity of result set
        num_counting_qubits = int(num_qubits) - num_state_qubits - 1
        counts, fidelity = analyze_and_print_result(qc, result, num_counting_qubits, int(s_int))
        metrics.store_metric(num_qubits, s_int, 'fidelity', fidelity)

    # Initialize execution module using the execution result handler above and specified backend_id
    ex.init_execution(execution_handler)
    ex.set_execution_target(backend_id)

    # Execute Benchmark Program N times for multiple circuit sizes
    # Accumulate metrics asynchronously as circuits complete
    for num_qubits in range(min_qubits, max_qubits + 1):

        # as circuit width grows, the number of counting qubits is increased
        num_counting_qubits = num_qubits - num_state_qubits - 1

        # determine number of circuits to execute for this group
        num_circuits = min(2 ** (num_counting_qubits), max_circuits)

        print(f"************\nExecuting [{num_circuits}] circuits with num_qubits = {num_qubits}")

        # determine range of secret strings to loop over
        if 2**(num_counting_qubits) <= max_circuits:
            s_range = list(range(num_circuits))
        else:
            s_range = np.random.choice(2**(num_counting_qubits), num_circuits, False)

        # loop over limited # of secret strings for this
        for s_int in s_range:
            # create the circuit for given qubit size and secret string, stor time metric
            ts = time.time()

            a_ = a_from_s_int(s_int, num_counting_qubits)

            qc = AmplitudeEstimation(num_state_qubits, num_counting_qubits, a_)
            metrics.store_metric(num_qubits, s_int, 'create_time', time.time() - ts)

            # submit circuit for execution on target (simulator, cloud simulator, or hardware)
            ex.submit_circuit(qc, num_qubits, s_int, num_shots)
        
        # execute all circuits for this group, aggregate and report metrics when complete
        ex.execute_circuits()
        metrics.aggregate_metrics_for_group(num_qubits)
        metrics.report_metrics_for_group(num_qubits)

    # Alternatively, execute all circuits, aggregate and report metrics
    # ex.execute_circuits()
    # metrics.aggregate_metrics_for_group(input_size)
    # metrics.report_metrics_for_group(input_size)

    # print a sample circuit
    print("Sample Circuit:"); print(QC_ if QC_ != None else "  ... too large!")
    print("\nControlled Quantum Operator 'cQ' ="); print(cQ_ if cQ_ != None else " ... too large!")
    print("\nQuantum Operator 'Q' ="); print(Q_ if Q_ != None else " ... too large!")
    print("\nAmplitude Generator 'A' ="); print(A_ if A_ != None else " ... too large!")
    print("\nInverse QFT Circuit ="); print(QFTI_ if QC_ != None else "  ... too large!")

    # Plot metrics for all circuit sizes
    metrics.plot_metrics("Benchmark Results - Amplitude Estimation - Braket")

# if main, execute method
if __name__ == '__main__': run()