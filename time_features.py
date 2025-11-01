"""
Time-based feature generation for ML models.
"""
import pandas as pd
import numpy as np
from datetime import datetime

def add_time_features(df):
    """
    Add time-based features to a dataframe with a datetime index.
    
    Args:
        df: Pandas DataFrame with datetime index or 'time' column
        
    Returns:
        DataFrame with added time features
    """
    
    # Create copy to avoid modifying original
    df = df.copy()
    
    # Convert time column to datetime if needed
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time')
    elif not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have datetime index or 'time' column")
    
    # Extract basic time components
    df['hour_of_day'] = df.index.hour
    df['minute_of_hour'] = df.index.minute
    df['day_of_week'] = df.index.dayofweek
    df['day_of_month'] = df.index.day
    df['week_of_year'] = df.index.isocalendar().week
    df['month'] = df.index.month
    df['quarter'] = df.index.quarter
    df['year'] = df.index.year
    
    # Trading sessions (rough approximation)
    df['session_as'] = (df['hour_of_day'] >= 0) & (df['hour_of_day'] < 8)  # Asia
    df['session_eu'] = (df['hour_of_day'] >= 8) & (df['hour_of_day'] < 16)  # Europe
    df['session_us'] = (df['hour_of_day'] >= 13) & (df['hour_of_day'] < 21)  # US
    
    # Day parts
    df['is_morning'] = (df['hour_of_day'] >= 6) & (df['hour_of_day'] < 12)
    df['is_afternoon'] = (df['hour_of_day'] >= 12) & (df['hour_of_day'] < 18)
    df['is_evening'] = (df['hour_of_day'] >= 18) & (df['hour_of_day'] < 24)
    df['is_night'] = (df['hour_of_day'] >= 0) & (df['hour_of_day'] < 6)
    
    # Weekend info
    df['is_weekend'] = df['day_of_week'].isin([5, 6])
    
    # Month start/end
    df['is_month_start'] = df.index.is_month_start
    df['is_month_end'] = df.index.is_month_end
    
    # Quarter start/end  
    df['is_quarter_start'] = df.index.is_quarter_start
    df['is_quarter_end'] = df.index.is_quarter_end
    
    # Year start/end
    df['is_year_start'] = df.index.is_year_start 
    df['is_year_end'] = df.index.is_year_end
    
    # Cyclical encoding of time features
    df['hour_sin'] = np.sin(df['hour_of_day'] * (2 * np.pi / 24))
    df['hour_cos'] = np.cos(df['hour_of_day'] * (2 * np.pi / 24))
    
    df['day_of_week_sin'] = np.sin(df['day_of_week'] * (2 * np.pi / 7))
    df['day_of_week_cos'] = np.cos(df['day_of_week'] * (2 * np.pi / 7))
    
    df['month_sin'] = np.sin((df['month'] - 1) * (2 * np.pi / 12))
    df['month_cos'] = np.cos((df['month'] - 1) * (2 * np.pi / 12))
    
    return df
