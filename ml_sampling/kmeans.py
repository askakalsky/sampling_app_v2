import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import pairwise_distances_argmin_min
import optuna
from sklearn.metrics import calinski_harabasz_score
from typing import Tuple, List
import logging
import datetime
import numpy as np
import heapq

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def kmeans_sampling(
    population_original: pd.DataFrame,
    population: pd.DataFrame,
    sample_size: int,
    features: List[str],
    random_seed: int
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """
    Performs sampling using K-Means clustering with Optuna-based hyperparameter optimization.
    The clustering quality is evaluated using dynamically selected metrics.

    Parameters:
    -----------
    population_original : pd.DataFrame
        Original dataset to apply clustering on.
    population : pd.DataFrame
        Preprocessed dataset with selected features for clustering.
    sample_size : int
        Number of samples to retrieve based on distance to cluster centroid.
    features : List[str]
        List of features used for clustering.
    random_seed : int
        Seed for random number generation.

    Returns:
    --------
    Tuple containing:
        - population_original : pd.DataFrame
          Original dataset with clustering results.
        - population : pd.DataFrame
          Preprocessed dataset with clustering results.
        - sample_processed : pd.DataFrame
          Subset of the dataset containing the selected samples.
        - method_description : str
          Description of the sampling process and parameters used.
        - study : optuna.Study
          The Optuna study object that contains the results of hyperparameter optimization.
    """
    try:
        # Copy the original data to avoid in-place modifications
        population_original = population_original.copy()
        population = population.copy()

        def objective(trial):
            # Define hyperparameters for K-Means
            params = {
                'n_clusters': trial.suggest_int('n_clusters', 2, 20),
                'init': 'k-means++',
                'n_init': trial.suggest_int('n_init', 5, 30),
                'max_iter': trial.suggest_int('max_iter', 100, 500)
            }

            # Fit KMeans with the current parameters
            kmeans = KMeans(random_state=random_seed, **params)
            kmeans.fit(population)

            # Get cluster labels
            labels = kmeans.labels_

            # Calculate Calinski-Harabasz score for the current clustering
            score = calinski_harabasz_score(population, labels)

            return score

        # Run Optuna optimization with the defined objective
        study = optuna.create_study(
            direction='maximize', sampler=optuna.samplers.TPESampler(seed=random_seed))
        study.optimize(objective, n_trials=100, show_progress_bar=True)

        # Best parameters after optimization
        best_params = study.best_params
        best_kmeans = KMeans(random_state=random_seed, **best_params)
        best_kmeans.fit(population)

        # Cluster predictions
        clusters = best_kmeans.predict(population)
        if not np.issubdtype(clusters.dtype, np.integer):
            clusters = clusters.astype(int)

        # Distance to centroids
        _, distances = pairwise_distances_argmin_min(
            population, best_kmeans.cluster_centers_)

        # Add columns for cluster assignment and distance to centroid
        population_original['distance_to_centroid'] = population['distance_to_centroid'] = distances
        population_original['cluster'] = population['cluster'] = clusters

        # Optimized sampling using largest distances
        if sample_size < len(population_original):
            largest_distances_indices = heapq.nlargest(
                sample_size, range(len(distances)), distances.take)
            sample_processed = population_original.iloc[largest_distances_indices]
        else:
            logger.warning(
                f"Requested sample size {sample_size} exceeds available data size {len(population_original)}. Using full data.")
            sample_processed = population_original

        # Mark the samples in both original and processed populations
        population_original['is_sample'] = population['is_sample'] = 0
        population_original.loc[sample_processed.index, 'is_sample'] = 1
        population.loc[sample_processed.index, 'is_sample'] = 1

        # Total population size and number of clusters
        population_size = len(population_original)
        num_clusters = best_params['n_clusters']

        # Method description
        method_description = (
            f"**SAMPLING**\n"
            f"K-Means sampling with hyperparameter optimization using Optuna.\n"
            f"Sample size: {sample_size}.\n"
            f"Total population size: {population_size}.\n"
            f"Number of clusters: {num_clusters}.\n"
            f"Features: {features}.\n"
            f"Best K-Means parameters: {best_params}.\n"
            f"Creation date and time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n"
            f"Random seed: {random_seed}.\n"
            f"Number of trials: {len(study.trials)}.\n"
        )

        return population_original, population, sample_processed, method_description, study

    except ValueError as ve:
        logger.error(f"ValueError: {ve}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), f"ValueError: {ve}", None

    except KeyError as ke:
        logger.error(f"KeyError: {ke}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), f"KeyError: {ke}", None

    except Exception as e:
        logger.exception(f"Unexpected error in kmeans_sampling: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), f"Unexpected error: {e}", None
