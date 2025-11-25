
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Container,
  Divider,
  Grid,
  Paper,
  Stack,
  Typography,
  keyframes,
} from '@mui/material';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  type AssessmentResponse,
  type AssessmentStatus,
  type ResultsState,
  type Side,
  SIDE_LABELS,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const POLL_INTERVAL_MS = 5000; // 5 seconds

// Animation keyframes for the pending state
const pulse = keyframes`
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
`;

/**
 * Normalizes backend AssessmentResponse.result to display-ready URLs.
 * For each side, extracts pickup_image and prefers annotated_return_image over return_image.
 */
function normalizeResults(
  results: AssessmentResponse['results']
): ResultsState {
  if (!results) return {};

  const normalized: ResultsState = {};
  for (const [side, sideData] of Object.entries(results)) {
    if (!sideData) continue;
    normalized[side as Side] = {
      pickupUrl: sideData.pickup_image,
      resultUrl: sideData.annotated_return_image ?? sideData.return_image,
    };
  }
  return normalized;
}

export default function AssessmentPage() {
  const { uploadId } = useParams<{ uploadId: string }>();
  const navigate = useNavigate();

  // Core state
  const [status, setStatus] = useState<AssessmentStatus | null>(null);
  const [results, setResults] = useState<ResultsState>({});
  const [summary, setSummary] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);

  // Track the last known status to detect changes (avoid unnecessary message updates)
  const lastStatusRef = useRef<AssessmentStatus | null>(null);

  // Ref to hold the polling interval ID
  const pollTimerRef = useRef<number | null>(null);

  // Ref to track if the component is mounted (prevent setState after unmounting)
  const isMountedRef = useRef(true);

  /**
   * Determines if polling should continue based on current status.
   */
  const shouldContinuePolling = useCallback((currentStatus: AssessmentStatus | null): boolean => {
    if (!currentStatus) return true;
    return !['complete', 'failed', 'not_found'].includes(currentStatus);
  }, []);

  /**
   * Fetches the current assessment status from the backend.
   * Only updates state if the status actually changed or if it's the first load.
   */
  const fetchAssessmentStatus = useCallback(async () => {
    if (!uploadId) return;

    try {
      const response = await axios.get<AssessmentResponse>(
        `${API_BASE_URL}/assessment/${uploadId}`
      );

      if (!isMountedRef.current) return;

      const status = response.data.status;
      const results = response.data.results;
      const summary = response.data.summary;

      // Only update state if status changed or this is the first load
      if (status !== lastStatusRef.current || isInitialLoading) {
        setStatus(status);
        lastStatusRef.current = status;

        if (results) {
          setResults(normalizeResults(results));
        }

        if (summary) {
          setSummary(summary);
        }

        // Clear any previous errors on successful fetch
        setError(null);
      }

      if (isInitialLoading) {
        setIsInitialLoading(false);
      }

      // Stop polling if we reached a terminal state
      if (!shouldContinuePolling(status)) {
        setIsPolling(false);
        if (pollTimerRef.current !== null) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    catch (e: any) {
      if (!isMountedRef.current) return;

      if (axios.isAxiosError(e)) {
        // Handle 404 specifically
        if (e.response?.status === 404) {
          setStatus('not_found');
          lastStatusRef.current = 'not_found';
          setIsPolling(false);
          if (pollTimerRef.current !== null) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          if (isInitialLoading) {
            setIsInitialLoading(false);
          }
          return;
        }

        // For other errors, show an error message but keep the last known status
        const message =
          e.response?.data?.detail ||
          e.response?.data?.message ||
          e.message ||
          'Unable to contact the assessment service. Please check your connection.';
        setError(message);
      } else {
        setError(
          e?.message ?? 'An unexpected error occurred while fetching assessment status.'
        );
      }

      if (isInitialLoading) {
        setIsInitialLoading(false);
      }
    }
  }, [uploadId, isInitialLoading, shouldContinuePolling]);

  /**
   * Start polling: fetch immediately, then set up interval.
   */
  const startPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      // Already polling, don't start another interval
      return;
    }

    // Poll every 5 seconds
    setIsPolling(true);
    pollTimerRef.current = window.setInterval(async () => {
      await fetchAssessmentStatus();
    }, POLL_INTERVAL_MS);
  }, [fetchAssessmentStatus]);

  /**
   * Stop polling and clean up interval.
   */
  const stopPolling = useCallback(() => {
    setIsPolling(false);
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  /**
   * Effect: Start polling on mount, clean up on unmount.
   */
  useEffect(() => {
    // if (!uploadId) {
    //   setError('No upload ID provided in the URL.');
    //   setIsInitialLoading(false);
    //   return;
    // }

    isMountedRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    startPolling();

    return () => {
      isMountedRef.current = false;
      stopPolling();
    };
  }, [uploadId, startPolling, stopPolling]);

  /**
   * Navigate back to the main page.
   */
  const handleBackToMain = useCallback(() => {
    navigate('/');
  }, [navigate]);

  /**
   * Render appropriate content based on current status.
   */
  const renderStatusContent = useMemo(() => {
    if (isInitialLoading) {
      return (
        <Stack spacing={2} alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
          <Typography variant="body1" color="text.secondary">
            Loading assessment status…
          </Typography>
        </Stack>
      );
    }

    if (!status) {
      return (
        <Alert severity="error">
          Unable to load assessment status. Please try again or return to the main page.
        </Alert>
      );
    }

    switch (status) {
      case 'pending':
        return (
          <Box>
            <Alert
              severity="warning"
              sx={{
                animation: `${pulse} 2s ease-in-out infinite`,
              }}
            >
              Your assessment is queued and has not started yet. This should only take a
              moment.
            </Alert>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              The page will automatically refresh every 5 seconds until your assessment
              begins.
            </Typography>
          </Box>
        );

      case 'in_progress':
        return (
          <Box>
            <Alert severity="info" icon={false}>
              <Stack direction="row" spacing={2} alignItems="center">
                <CircularProgress size={24} />
                <Box>
                  <Typography variant="body1" fontWeight="medium">
                    Assessment in progress…
                  </Typography>
                  <Typography variant="body2">
                    This may take up to a few minutes. Feel free to return to this page at any time.
                  </Typography>
                </Box>
              </Stack>
            </Alert>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              We're analyzing your images for damage. The page will automatically update
              when complete.
            </Typography>
          </Box>
        );

      case 'complete':
        return (
          <Box>
            <Alert severity="success" sx={{ mb: 3 }}>
              Assessment complete! Your results are ready.
            </Alert>

            {Object.keys(results).length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No results available for this assessment.
              </Typography>
            ) : (
              <Stack spacing={4}>
                <Typography variant="body2" color="text.secondary">
                  Where differences are highlighted, new damage was detected on return.
                </Typography>

                {Object.entries(results).map(([side, displayResult]) => {
                  const sideLabel =
                    SIDE_LABELS[side as Side] ?? side.charAt(0).toUpperCase() + side.slice(1);

                  return (
                    <Paper key={side} variant="outlined" sx={{ p: 3 }}>
                      <Typography variant="h6" gutterBottom>
                        {sideLabel}
                      </Typography>
                      <Divider sx={{ mb: 2 }} />
                      <Grid container spacing={2}>
                        {/* Pickup image */}
                        <Grid size={{ xs: 12, md: 6 }}>
                          <Typography
                            variant="subtitle2"
                            color="text.secondary"
                            gutterBottom
                          >
                            On Pickup
                          </Typography>
                          <Box
                            component="img"
                            src={displayResult.pickupUrl}
                            alt={`${sideLabel} - Pickup`}
                            sx={{
                              maxWidth: '100%',
                              maxHeight: 320,
                              objectFit: 'contain',
                              borderRadius: 1,
                              border: '1px solid',
                              borderColor: 'divider',
                            }}
                          />
                        </Grid>

                        {/* Return image */}
                        <Grid size={{ xs: 12, md: 6 }}>
                          <Typography
                            variant="subtitle2"
                            color="text.secondary"
                            gutterBottom
                          >
                            On Return
                          </Typography>
                          <Box
                            component="img"
                            src={displayResult.resultUrl}
                            alt={`${sideLabel} - Return`}
                            sx={{
                              maxWidth: '100%',
                              maxHeight: 320,
                              objectFit: 'contain',
                              borderRadius: 1,
                              border: '1px solid',
                              borderColor: 'divider',
                            }}
                          />
                        </Grid>
                      </Grid>
                    </Paper>
                  );
                })}
              </Stack>
            )}
             <Typography margin={3} variant="body1" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>
                {summary}
             </Typography>

            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Button variant="contained" color="primary" onClick={handleBackToMain}>
                Start Another Assessment
              </Button>
            </Box>
          </Box>
        );

      case 'failed':
        return (
          <Box>
            <Alert severity="error" sx={{ mb: 2 }}>
              The assessment could not be completed. This may be due to an issue
              processing your images. Please submit a new assessment with different images
              or contact support if the problem persists.
            </Alert>
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Button variant="contained" color="primary" onClick={handleBackToMain}>
                Back to Main Page
              </Button>
            </Box>
          </Box>
        );

      case 'not_found':
        return (
          <Box>
            <Alert severity="error" sx={{ mb: 2 }}>
              No assessment was found for this link. It may have expired or never existed.
              Please start a new assessment from the main page.
            </Alert>
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <Button variant="contained" color="primary" onClick={handleBackToMain}>
                Back to Main Page
              </Button>
            </Box>
          </Box>
        );

      default:
        return (
          <Alert severity="warning">
            Unknown assessment status: {status}. Please contact support.
          </Alert>
        );
    }
  }, [isInitialLoading, status, results, summary, handleBackToMain]);

  return (
    <Container maxWidth="md">
      <Box sx={{ my: 4 }}>
        <Card elevation={3}>
          <CardHeader
            title="Assessment Status"
            subheader="We're analyzing your images. This may take a short while."
          />
          <CardContent>
            <Stack spacing={3}>
              {/* Network/Connection errors */}
              {error && (
                <Alert severity="error" onClose={() => setError(null)}>
                  {error}
                </Alert>
              )}

              {/* Status-specific content */}
              {renderStatusContent}

              {/* Polling indicator (only show when actively polling and not initial load) */}
              {isPolling && !isInitialLoading && status && ['pending', 'in_progress'].includes(status) && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ textAlign: 'center', fontStyle: 'italic' }}
                >
                  Refreshing automatically every 5 seconds…
                </Typography>
              )}
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
}
