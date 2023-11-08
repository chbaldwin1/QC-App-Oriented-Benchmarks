#
# pyTKET Executor Interface 
#
# This module implements the 'executor' intercept for execution with pyTKET 
#


from pytket.extensions.qiskit import qiskit_to_tk
try:
    # if pytket-quantinuum is installed and have login
    from pytket.extensions.quantinuum import QuantinuumBackend
    machine = 'H1-1E'  # change to H1-1 for real machine
    backend = QuantinuumBackend(device_name=machine)
    backend.login()
except:
    # else use Aer with pytket-qiskit (hit escape with login)
    print('Using qiskit Aer through pytket')
    from pytket.extensions.qiskit import AerBackend
    backend = AerBackend()
    

class PytketResult(object):

    def __init__(self, quantinuum_result):
        # super().__init__()
        self.quantinuum_result = quantinuum_result

        # Code to match qiskit outputs
        cregs = {}
        for cname in list(self.quantinuum_result.get_bitlist())[::-1]:
            name, ind = cname.__str__()[:-1].split('[')
            try:
                cregs[name] += 1
            except KeyError:
                cregs[name] = 1
        counts = self.quantinuum_result.get_counts()
        self.counts = {}
        for key, val in counts.items():
            bit_list = ''
            bit = 0
            for length in cregs.values():
                bit_list += ''.join([str(i) for i in key[bit:bit + length]])
                bit_list += ' '
                bit += length
            bit_list = bit_list[:-1]
            self.counts[bit_list[::-1]] = val

    def get_counts(self, qc=None):
        counts = self.counts       
        return counts


# This function is called by the QED-C execution pipeline when specified as the 'executor'       
def run(qc, backend_name, backend_provider, shots=100):

    # backend_name defaults to 'qasm_simulator'
    circ = qiskit_to_tk(qc)
    circ =  backend.get_compiled_circuit(circ, optimisation_level=1)
    job = backend.process_circuit(circ, n_shots=shots)

    res = backend.get_result(job)
    result = PytketResult(res)

    result.exec_time = 0  # not sure how to get time info
    
    return result