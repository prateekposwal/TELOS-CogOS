import numpy as np
from telos.representations.transform import RepresentationTransform, RuntimeState

class CartesianTransform(RepresentationTransform):
    @property
    def name(self) -> str: return "cartesian"
    
    def forward(self, input_data: np.ndarray) -> np.ndarray:
        return input_data
        
    def inverse(self, action: np.ndarray) -> np.ndarray:
        return action
        
    def applicable(self, state: RuntimeState) -> float:
        return 1.0

class PolarTransform(RepresentationTransform):
    @property
    def name(self) -> str: return "polar"
    
    def forward(self, input_data: np.ndarray) -> np.ndarray:
        x, y = input_data[0], input_data[1]
        r = np.sqrt(x**2 + y**2)
        theta = np.arctan2(y, x)
        return np.array([r, theta])
        
    def inverse(self, action: np.ndarray) -> np.ndarray:
        r, theta = action[0], action[1]
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        return np.array([x, y])
        
    def applicable(self, state: RuntimeState) -> float:
        # Polar is better when state is far from origin
        return float(np.clip(np.linalg.norm(state.health_vector) / 5.0, 0.0, 1.0))
