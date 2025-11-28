from evaluation import calculate_performance_metrics
import pandas as pd
s = pd.Series([1000.0, 1016.0], index=pd.to_datetime(['2025-01-01','2025-01-02']))
print(calculate_performance_metrics(s, pd.DataFrame()))