import { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Backdrop,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Container,
  Divider,
  FormHelperText,
  Grid,
  Stack,
  Typography,
  CircularProgress,
  Paper,
} from '@mui/material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import './App.css';
import {
    ALL_SIDES,
    type Side,
    SIDE_LABELS, type UploadResponse,
} from './types';

type SideFiles = {
  pickup?: File;
  return?: File;
};

type FilesState = Partial<Record<Side, SideFiles>>;

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

function App() {
  const navigate = useNavigate();

  const [selectedSides, setSelectedSides] = useState<Side[]>([]);
  const [files, setFiles] = useState<FilesState>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const hasSelectedSides = useMemo(
    () => selectedSides.length > 0,
    [selectedSides],
  );

  const handleSideToggle = (side: Side) => {
    // Clear any previous errors when the selection changes
    setError(null);
    setValidationErrors([]);
    setSelectedSides((prev) =>
      prev.includes(side) ? prev.filter((s) => s !== side) : [...prev, side],
    );
  };

  const handleFileChange = useCallback(
    (side: Side, phase: 'pickup' | 'return', fileList: FileList | null) => {
      setError(null);
      setValidationErrors([]);
      const file = fileList?.[0];
      if (!file) return;

      setFiles((prev) => ({
        ...prev,
        [side]: {
          ...(prev[side] ?? {}),
          [phase]: file,
        },
      }));
    },
    [],
  );

  const validateForm = useCallback((): boolean => {
    const errors: string[] = [];

    if (selectedSides.length === 0) {
      errors.push('Please select at least one car side to inspect.');
    }

    selectedSides.forEach((side) => {
      const sideFiles = files[side] || {};
      if (!sideFiles.pickup || !sideFiles.return) {
        errors.push(
          `${SIDE_LABELS[side]}: please upload both pickup and return images.`,
        );
      }
    });

    setValidationErrors(errors);
    return errors.length === 0;
  }, [files, selectedSides]);

  const handleSubmit = async () => {
    setError(null);
    setValidationErrors([]);

    if (!validateForm()) {
      return;
    }

    const formData = new FormData();

    selectedSides.forEach((side) => {
      const sideFiles = files[side]!;
      // Field names per spec: `${side}-pickup` / `${side}-return`
      if (sideFiles.pickup) {
        formData.append(`${side}-pickup`, sideFiles.pickup);
      }
      if (sideFiles.return) {
        formData.append(`${side}-return`, sideFiles.return);
      }
    });

    try {
      setIsLoading(true);
        const response = await axios.post<UploadResponse>(
            `${API_BASE_URL}/upload`,
            formData,
            {
                headers: {
                    'Content-Type': 'multipart/form-data',
                }
            },
        );

      const uploadId = response.data.upload_id;
      if (!uploadId) {
        setError(
          'Upload response did not include an assessment ID. Please try again or contact support.',
        );
        return;
      }

      // Navigate to a dedicated assessment status page
      navigate(`/assessment/${uploadId}`);
    } catch (e: any) {
      if (axios.isAxiosError(e)) {
        const message =
          e.response?.data?.detail ||
          e.response?.data?.message ||
          e.message ||
          'An unexpected error occurred while starting the assessment.';
        setError(message);
      } else {
        setError(
          e?.message ??
            'An unexpected error occurred while starting the assessment.',
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  const resetForm = () => {
    setSelectedSides([]);
    setFiles({});
    setError(null);
    setValidationErrors([]);
  };

  const isSideIncomplete = (side: Side) => {
    const sideFiles = files[side];
    return !sideFiles?.pickup || !sideFiles?.return;
  };

  return (
    <>
      <Container maxWidth="md">
        <Box sx={{ my: 4 }}>
          <Card elevation={3}>
            <CardHeader
              title="Car Damage Assessment"
              subheader="Select car sides, upload pickup and return images, then run damage assessment."
            />
            <CardContent>
              <Stack spacing={3}>
                {error && (
                  <Alert
                    severity="error"
                    onClose={() => setError(null)}
                    sx={{ textAlign: 'left' }}
                  >
                    {error}
                  </Alert>
                )}

                {validationErrors.length > 0 && (
                  <Alert
                    severity="warning"
                    onClose={() => setValidationErrors([])}
                    sx={{ textAlign: 'left' }}
                  >
                    <ul style={{ margin: 0, paddingLeft: '1.2rem' }}>
                      {validationErrors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </Alert>
                )}

                {/* Side selection */}
                <Box>
                  <Typography variant="subtitle1" gutterBottom>
                    1. Select car sides to inspect
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    gutterBottom
                  >
                    Choose one or more sides. You can inspect up to four sides at
                    once.
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    flexWrap="wrap"
                    sx={{ mt: 1 }}
                  >
                    {ALL_SIDES.map((side) => {
                      const selected = selectedSides.includes(side);
                      return (
                        <Chip
                          key={side}
                          label={SIDE_LABELS[side]}
                          color={selected ? 'primary' : 'default'}
                          variant={selected ? 'filled' : 'outlined'}
                          onClick={() => handleSideToggle(side)}
                          disabled={isLoading}
                          sx={{ mr: 1, mb: 1 }}
                          aria-pressed={selected}
                        />
                      );
                    })}
                  </Stack>
                  <FormHelperText>
                    At least one side is required before running the assessment.
                  </FormHelperText>
                </Box>

                <Divider />

                {/* Image uploads per selected side */}
                <Box>
                  <Typography variant="subtitle1" gutterBottom>
                    2. Upload pickup and return images
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    gutterBottom
                  >
                    For each selected side, upload exactly one pickup and one
                    return image (JPEG or PNG).
                  </Typography>

                  {selectedSides.length === 0 && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mt: 2 }}
                    >
                      No sides selected yet. Choose at least one side above.
                    </Typography>
                  )}

                  <Stack spacing={2} sx={{ mt: 2 }}>
                    {selectedSides.map((side) => {
                      const sideFiles = files[side] || {};
                      const pickupFile = sideFiles.pickup;
                      const returnFile = sideFiles.return;

                      return (
                        <Paper
                          key={side}
                          variant="outlined"
                          sx={{ p: 2, textAlign: 'left' }}
                        >
                          <Typography variant="subtitle1" gutterBottom>
                            {SIDE_LABELS[side]}
                          </Typography>
                          <Grid container spacing={2}>
                            {/* Pickup upload */}
                            <Grid size={{ xs: 12, md: 6 }}>
                              <Typography
                                variant="body2"
                                color="text.secondary"
                                gutterBottom
                              >
                                Pickup image
                              </Typography>
                              <Button
                                variant="outlined"
                                component="label"
                                disabled={isLoading}
                              >
                                {pickupFile
                                  ? 'Change pickup image'
                                  : 'Upload pickup'}
                                <input
                                  type="file"
                                  accept="image/*"
                                  hidden
                                  onChange={(e) =>
                                    handleFileChange(
                                      side,
                                      'pickup',
                                      e.target.files,
                                    )
                                  }
                                />
                              </Button>
                              {pickupFile && (
                                <Typography
                                  variant="caption"
                                  sx={{ display: 'block', mt: 1 }}
                                >
                                  Selected: {pickupFile.name}
                                </Typography>
                              )}
                            </Grid>

                            {/* Return upload */}
                            <Grid size={{ xs: 12, md: 6 }}>
                              <Typography
                                variant="body2"
                                color="text.secondary"
                                gutterBottom
                              >
                                Return image
                              </Typography>
                              <Button
                                variant="outlined"
                                component="label"
                                disabled={isLoading}
                              >
                                {returnFile
                                  ? 'Change return image'
                                  : 'Upload return'}
                                <input
                                  type="file"
                                  accept="image/*"
                                  hidden
                                  onChange={(e) =>
                                    handleFileChange(
                                      side,
                                      'return',
                                      e.target.files,
                                    )
                                  }
                                />
                              </Button>
                              {returnFile && (
                                <Typography
                                  variant="caption"
                                  sx={{ display: 'block', mt: 1 }}
                                >
                                  Selected: {returnFile.name}
                                </Typography>
                              )}
                            </Grid>
                          </Grid>

                          {isSideIncomplete(side) && (
                            <FormHelperText error sx={{ mt: 1 }}>
                              Both pickup and return images are required for this
                              side.
                            </FormHelperText>
                          )}
                        </Paper>
                      );
                    })}
                  </Stack>
                </Box>

                {/* Submit / actions */}
                <Box sx={{ mt: 1 }}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={2}
                    justifyContent="flex-end"
                    alignItems={{ xs: 'stretch', sm: 'center' }}
                  >
                    <Button
                      variant="text"
                      color="inherit"
                      onClick={resetForm}
                      disabled={isLoading}
                    >
                      Clear form
                    </Button>
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={handleSubmit}
                      disabled={isLoading || !hasSelectedSides}
                    >
                      Run Assessment
                    </Button>
                  </Stack>
                  <FormHelperText sx={{ mt: 1 }}>
                    The assessment may take a few moments. After upload, you&apos;ll
                    be taken to a status page. Save the upload id to refer to the
                      assessment later. Note that uploaded files and assessment
                      data are only stored for three days.
                  </FormHelperText>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      </Container>

      {/* Loading backdrop during upload */}
      <Backdrop
        open={isLoading}
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 1 }}
      >
        <Stack spacing={2} alignItems="center">
          <CircularProgress color="inherit" />
          <Typography>Starting assessment…</Typography>
        </Stack>
      </Backdrop>
    </>
  );
}

export default App;