'''
	Mstar bin firmware packer
'''

'''
	Header structure
	-------
	Multi-line script which contains MBOOT commands
	The header script ends with line: '% <- this is end of file symbol'
	Line separator is '\n'
	The header is filled by 0xFF to 16KB
	The header size is always 16KB
'''

'''
	Bin structure
	-------
	Basically it's merged parts:

	[part 1]
	[part 2]
	....
	[part n]

	Each part is 4 byte aligned (filled by 0xFF)
'''

'''
	Footer structure
	|MAGIC|SWAPPED HEADER CRC32|SWAPPED BIN CRC32|FIRST 16 BYTES OF HEADER|
'''

import configparser
import sys
import time
import os
import struct
import utils

tmpDir = 'tmp'
headerPart = os.path.join(tmpDir, '~header')
binPart = os.path.join(tmpDir, '~bin') 
footerPart = os.path.join(tmpDir, '~footer') 

# Command line args
if len(sys.argv) == 1: 
	print ("Usage: pack.py <config file>")
	print ("Example: pack.py configs/letv-x355pro.ini")
	quit()

configFile = sys.argv[1]

# Parse config file
config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
#config = configparser.ConfigParser()
config.read(configFile)

# Main
main = config['Main'];
firmwareFileName = main['FirmwareFileName']
projectFolder = main['ProjectFolder']
useHexValues = main['UseHexValues']

SCRIPT_FIRMWARE_FILE_NAME = main['SCRIPT_FIRMWARE_FILE_NAME']
DRAM_BUF_ADDR = main['DRAM_BUF_ADDR']
MAGIC_FOOTER = main['MAGIC_FOOTER']
HEADER_SIZE = utils.sizeInt(main['HEADER_SIZE'])

# Header
header = config['HeaderScript'];
headerScriptPrefix = config.get('HeaderScript', 'Prefix', raw = True)
headerScriptSuffix = config.get('HeaderScript', 'Suffix', raw = True)

# Parts
#parts = filter(lambda value: "part/" not in value, config.sections())
parts = list(filter(lambda s: s.startswith('part/'), config.sections()))
#parts = list(map(lambda x: x.replace('part/', ''), parts))

print (parts)

print("\n")
print ("[i] Date: {}".format(time.strftime("%d/%m/%Y %H:%M:%S")))
print ("[i] Firmware file name: {}".format(firmwareFileName))
print ("[i] Project folder: {}".format(projectFolder))
print ("[i] Use hex values: {}".format(useHexValues))
print ("[i] Script firmware filename: {}".format(SCRIPT_FIRMWARE_FILE_NAME))
print ("[i] DRAM_BUF_ADDR: {}".format(DRAM_BUF_ADDR))
print ("[i] MAGIC_FOOTER: {}".format(MAGIC_FOOTER))
print ("[i] HEADER_SIZE: {}".format(HEADER_SIZE))

# Create working directory
print ('[i] Create working directory ...')
utils.createDirectory(tmpDir)

print ('[i] Generating header and bin ...')
# Initial empty bin to store merged parts
open(binPart, 'w').close()

with open(headerPart, 'wb') as header:
	header.write('# Header prefix'.encode())
	header.write(headerScriptPrefix.encode())
	header.write('\n\n'.encode())

	header.write('# Partitions'.encode())
	for sectionName in parts:

		part = config[sectionName]
		name = sectionName.replace('part/', '')
		create = utils.str2bool(utils.getConfigValue(part, 'create', ''))
		size = utils.getConfigValue(part, 'size', 'NOT_SET')
		erase = utils.str2bool(utils.getConfigValue(part, 'erase', ''))
		type = utils.getConfigValue(part, 'type', 'NOT_SET')
		imageFile = utils.getConfigValue(part, 'imageFile', 'NOT_SET')
		chunkSize = utils.sizeInt(utils.getConfigValue(part, 'chunkSize', '0'))
		lzo = utils.str2bool(utils.getConfigValue(part, 'lzo', ''))

		print("\n")
		print("[i] Processing partition")
		print("[i]      Name: {}".format(name))
		print("[i]      Create: {}".format(create))
		print("[i]      Size: {}".format(size))
		print("[i]      Erase: {}".format(erase))
		print("[i]      Type: {}".format(type))
		print("[i]      Image: {}".format(imageFile))
		print("[i]      LZO: {}".format(lzo))

		header.write('\n'.encode())
		header.write('# {}\n'.format(name).encode())

		if (create):
			header.write('mmc create {} {}\n'.format(name, size).encode())

		if (erase):
			header.write('mmc erase.p {}\n'.format(name).encode())

		if (type == 'partitionImage'):
			
			if (chunkSize > 0):
				print ('[i] Splitting ...')
				chunks = utils.splitFile(imageFile, tmpDir, chunksize = chunkSize)
			else:
				# It will contain whole image as a single chunk
				chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)

			for index, inputChunk in enumerate(chunks):
				print ('[i] Processing chunk: {}'.format(inputChunk))
				(name1, ext1) = os.path.splitext(inputChunk)
				if lzo:
					outputChunk = name1 + '.lzo'
					print ('[i]     LZO: {} -> {}'.format(inputChunk, outputChunk))
					utils.lzo(inputChunk, outputChunk)
				else:
					outputChunk = inputChunk

				size = os.path.getsize(outputChunk)
				offset = os.path.getsize(binPart) + HEADER_SIZE 
				header.write('filepartload {} {} {:02X} {:02X}\n'.format(DRAM_BUF_ADDR, SCRIPT_FIRMWARE_FILE_NAME, offset, size).encode())

				print ('[i]     Align chunk')
				utils.alignFile(outputChunk)

				print ('[i]     Append: {} -> {}'.format(outputChunk, binPart))
				utils.appendFile(outputChunk, binPart)

				if lzo:
					if index == 0:
						header.write('mmc unlzo {} {:02X} {} 1\n'.format(DRAM_BUF_ADDR, size, name).encode())
					else:
						header.write('mmc unlzo.cont {} {:02X} {} 1\n'.format(DRAM_BUF_ADDR, size, name).encode())
				else:
					if len(chunks) == 1:
						header.write('mmc write.p {} {} {:02X} 1\n'.format(DRAM_BUF_ADDR, name, size).encode())
					else:
						# filepartload 50000000 MstarUpgrade.bin e04000 c800000
						# mmc write.p.continue 50000000 system 0 c800000 1

						# filepartload 50000000 MstarUpgrade.bin d604000 c800000
						# mmc write.p.continue 50000000 system 64000 c800000 1
						# Why offset is 64000 but not c800000 ???
						print ('[!] UNSUPPORTED: mmc write.p.continue')
						quit()

		if (type == 'secureInfo'):

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = os.path.getsize(outputChunk)
			offset = os.path.getsize(binPart) + HEADER_SIZE 
			header.write('filepartload {} {} {:02X} {:02X}\n'.format(DRAM_BUF_ADDR, SCRIPT_FIRMWARE_FILE_NAME, offset, size).encode())

			print ('[i]     Align')
			utils.alignFile(outputChunk)

			print ('[i]     Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)

			header.write('store_secure_info {} {}\n'.format(name, DRAM_BUF_ADDR).encode())

		if (type == 'nuttxConfig'):

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = os.path.getsize(outputChunk)
			offset = os.path.getsize(binPart) + HEADER_SIZE 
			header.write('filepartload {} {} {:02X} {:02X}\n'.format(DRAM_BUF_ADDR, SCRIPT_FIRMWARE_FILE_NAME, offset, size).encode())

			print ('[i]     Align')
			utils.alignFile(outputChunk)

			print ('[i]     Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)

			header.write('store_nuttx_config {} {}\n'.format(name, DRAM_BUF_ADDR).encode())

		if (type == 'sboot'):

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = os.path.getsize(outputChunk)
			offset = os.path.getsize(binPart) + HEADER_SIZE 
			header.write('filepartload {} {} {:02X} {:02X}\n'.format(DRAM_BUF_ADDR, SCRIPT_FIRMWARE_FILE_NAME, offset, size).encode())

			print ('[i]     Align')
			utils.alignFile(outputChunk)

			print ('[i]     Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)

			header.write('mmc write.boot 1 {} 0 {:02X}\n'.format(DRAM_BUF_ADDR, size).encode())

	header.write('\n'.encode())
	header.write('# Header suffix'.encode())
	header.write(headerScriptSuffix.encode())
	header.write('\n'.encode())

	header.write('% <- this is end of file symbol\n'.encode())
	header.flush()

	print ('[i] Fill header script to 16KB')
	header.write( ('\xff' * (HEADER_SIZE - os.path.getsize(headerPart))).encode(encoding='iso-8859-1') ) 

print ('[i] Generating footer ...')
headerCRC = utils.crc32(headerPart)
binCRC = utils.crc32(binPart)
header16bytes = utils.loadPart(headerPart, 0, 16)
with open(footerPart, 'wb') as footer:
	print ('[i]     Magic: {}'.format(MAGIC_FOOTER))
	footer.write(MAGIC_FOOTER.encode())
	print ('[i]     Header CRC: 0x{:02X}'.format(headerCRC))
	footer.write(struct.pack('L', headerCRC)) # struct.pack('L', data) <- returns byte swapped data
	print ('[i]     Bin CRC: 0x{:02X}'.format(binCRC))
	footer.write(struct.pack('L', binCRC))
	print ('[i]     First 16 bytes of header: {}'.format(header16bytes))
	footer.write(header16bytes)

print ('[i] Merging header, bin, footer ...')
open(firmwareFileName, 'w').close()
utils.appendFile(headerPart, firmwareFileName)
utils.appendFile(binPart, firmwareFileName)
utils.appendFile(footerPart, firmwareFileName)

shutil.rmtree(tmpDir)
print ('[i] Done')