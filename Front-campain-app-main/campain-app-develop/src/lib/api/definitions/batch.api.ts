import type { ApiRequest } from '../ApiRequest';

export const batchApi = {
  run: (): ApiRequest => ({
    url: '/batch/run',
    method: 'POST',
  }),
};
