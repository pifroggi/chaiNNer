import { Edge, Node } from 'reactflow';
import batchUpscale from './PRESET -- batch_upscale.json';
import captionedMultiUpscaleComparison from './PRESET -- captioned_multi_upscale_comparison.json';
import captionedUpscale from './PRESET -- captioned_upscale.json';
import separatedTransparencyUpscale from './PRESET -- separated_transaprency_upscale.json';

export interface PresetFile {
    version: string;
    content: {
        nodes: Node<unknown>[];
        edges: Edge<unknown>[];
    }; // SaveData;
    timestamp?: string;
    checksum?: string;
    migration?: number;
}

export interface Preset {
    name: string;
    author: string;
    description: string;
    chain: PresetFile;
}

export const presets = [
    {
        name: 'Separated Transparency Upscale',
        author: 'chaiNNer',
        description: 'A simple way of upscaling the RGB and Alpha channels separately.',
        chain: separatedTransparencyUpscale,
    },
    {
        name: 'Batch Upscale',
        author: 'chaiNNer',
        description: 'A simple example of a batch upscale.',
        chain: batchUpscale,
    },
    {
        name: 'Captioned Upscale',
        author: 'chaiNNer',
        description: 'Upscaling and attaching a caption to the output.',
        chain: captionedUpscale,
    },
    {
        name: 'Captioned Multi-Upscale Comparison',
        author: 'chaiNNer',
        description:
            'Upscaling with multiple models and making a comparison between them, with captions.',
        chain: captionedMultiUpscaleComparison,
    },
];